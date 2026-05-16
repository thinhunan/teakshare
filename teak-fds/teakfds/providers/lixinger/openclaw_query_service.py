# -*- coding: utf-8 -*-
"""
为 OpenClaw skill 提供统一查询接口：
1. 先查本地 SQLite
2. 缺失或实时数据过期时，走线上抓取
3. 查询结果回写 SQLite
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# 添加项目根目录到 Python 路径
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# 使用相对导入
from .db import Database
from .lixinger_spider import LixingerSpider


class LixingerQueryService:
    """个股/指数查询服务（带本地缓存与自动刷新）"""

    DEFAULT_PROJECT_ROOT = "/Users/Think/agents_documents/lixinger_crawl"

    def __init__(
        self,
        project_root: Optional[str] = None,
        settings_path: Optional[str] = None,
        cookie_path: Optional[str] = None,
        db_path: Optional[str] = None,
        force_use_cookie: bool = True,
        realtime_ttl_minutes: int = 120,
    ):
        base = project_root or self.DEFAULT_PROJECT_ROOT
        self.project_root = os.path.abspath(base)

        # 配置文件和 Cookie 默认在 scripts 子目录
        scripts_dir = os.path.join(self.project_root, "scripts")
        self.settings_path = os.path.abspath(
            settings_path or os.path.join(scripts_dir, "settings.json")
        )
        self.cookie_path = os.path.abspath(
            cookie_path or os.path.join(scripts_dir, "cookie.txt")
        )
        self.db_path = os.path.abspath(db_path or os.path.join(self.project_root, "db/lixinger.db"))

        self.force_use_cookie = force_use_cookie
        self.realtime_ttl_minutes = realtime_ttl_minutes

        self.db = Database(self.db_path)
        self._spider: Optional[LixingerSpider] = None

    def _ensure_spider(self) -> LixingerSpider:
        if self._spider is None:
            self._spider = LixingerSpider(
                settings_path=self.settings_path,
                cookie_path=self.cookie_path,
                db_path=self.db_path,
                auto_save=False,
                force_use_cookie=self.force_use_cookie,
            )
        return self._spider

    @staticmethod
    def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        return None

    @staticmethod
    def _parse_date(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return None

    def _is_stock_info_fresh(self, info: dict) -> bool:
        updated_at = self._parse_datetime(info.get("updated_at"))
        if not updated_at:
            return False
        return datetime.now() - updated_at <= timedelta(minutes=self.realtime_ttl_minutes)

    @staticmethod
    def _latest_expected_market_date(now: Optional[datetime] = None) -> datetime:
        current = now or datetime.now()
        # 周一早上、周末时，最新交易日可能是上周五
        weekday = current.weekday()
        if weekday == 0:
            return current - timedelta(days=3)
        if weekday == 6:
            return current - timedelta(days=2)
        if weekday == 5:
            return current - timedelta(days=1)
        return current - timedelta(days=1)

    def _is_daily_latest(self, latest_date: Optional[str]) -> bool:
        latest = self._parse_date(latest_date)
        if not latest:
            return False
        expected = self._latest_expected_market_date()
        return latest.date() >= expected.date()

    def _refresh_from_online(self, code: str, granularity: str = "y10") -> Dict:
        spider = self._ensure_spider()
        data = spider.get_comprehensive_data(code, granularity=granularity, save_to_db=True)
        if not data:
            detail = getattr(spider, "last_error", None) or "未知错误"
            raise RuntimeError(
                f"线上抓取失败（仅重试一次后终止）: code={code}, granularity={granularity}, error={detail}"
            )
        return {
            "code": code,
            "name": data.stock_info.name,
            "stock_id": data.stock_info.stock_id,
            "fetched": True,
            "granularity": granularity,
            "daily_count": len(data.daily_data),
        }

    def _ensure_stock_info(self, code: str, realtime: bool = False) -> Dict:
        info = self.db.get_stock_info(code)
        if info:
            if realtime and (not self._is_stock_info_fresh(info)):
                self._refresh_from_online(code, granularity="y1")
                info = self.db.get_stock_info(code)
            if info:
                return info

        self._refresh_from_online(code, granularity="y10")
        info = self.db.get_stock_info(code)
        if not info:
            raise RuntimeError(f"数据库不存在标的信息: {code}")
        return info

    def get_supported_data_types(self) -> Dict:
        return {
            "asset_types": ["company", "index"],
            "interfaces": [
                "query_overview",
                "query_history",
                "query_statistics",
                "query_report_impacts",
                "refresh_asset",
                "screen_undervalued_stocks",
            ],
            "fields": {
                "overview": ["stock_info", "latest_daily"],
                "history": ["daily_metrics"],
                "statistics": ["metric_statistics"],
                "impacts": ["report_impacts"],
                "screener": ["undervalued_stocks"],
            },
        }

    def query_asset_overview(self, code: str, realtime: bool = False) -> Dict:
        info = self._ensure_stock_info(code, realtime=realtime)

        latest_daily = self.db.get_latest_daily_metric(info["stock_id"])
        if realtime and (not latest_daily or not self._is_daily_latest(latest_daily.get("date"))):
            self._refresh_from_online(code, granularity="y1")
            info = self.db.get_stock_info(code) or info
            latest_daily = self.db.get_latest_daily_metric(info["stock_id"])

        return {
            "source": "sqlite",
            "code": code,
            "stock_info": info,
            "latest_daily": latest_daily,
        }

    def query_asset_history(
        self,
        code: str,
        limit: int = 250,
        ensure_latest: bool = False,
        refresh_if_missing: bool = True,
    ) -> Dict:
        info = self._ensure_stock_info(code, realtime=False)
        rows = self.db.get_daily_metrics(info["stock_id"], limit=limit if limit > 0 else None)

        if refresh_if_missing and not rows:
            self._refresh_from_online(code, granularity="fs")
            rows = self.db.get_daily_metrics(info["stock_id"], limit=limit if limit > 0 else None)

        if ensure_latest:
            latest_date = rows[0]["date"] if rows else None
            if not self._is_daily_latest(latest_date):
                self._refresh_from_online(code, granularity="y1")
                rows = self.db.get_daily_metrics(info["stock_id"], limit=limit if limit > 0 else None)

        return {
            "source": "sqlite",
            "code": code,
            "stock_info": info,
            "daily_metrics": rows,
            "count": len(rows),
        }

    def query_asset_statistics(
        self,
        code: str,
        granularity: str = "fs",
        realtime: bool = False,
        refresh_if_missing: bool = True,
    ) -> Dict:
        info = self._ensure_stock_info(code, realtime=realtime)
        stats = self.db.get_metric_statistics(info["stock_id"], granularity=granularity)

        if refresh_if_missing and not stats:
            # 优先尝试按目标粒度拉取；无结果再补 fs
            self._refresh_from_online(code, granularity=granularity)
            stats = self.db.get_metric_statistics(info["stock_id"], granularity=granularity)
            if not stats and granularity != "fs":
                self._refresh_from_online(code, granularity="fs")
                stats = self.db.get_metric_statistics(info["stock_id"], granularity="fs")

        if realtime and stats:
            latest_daily = self.db.get_latest_daily_metric(info["stock_id"])
            if not latest_daily or not self._is_daily_latest(latest_daily.get("date")):
                self._refresh_from_online(code, granularity="y1")
                stats = self.db.get_metric_statistics(info["stock_id"], granularity=granularity)

        return {
            "source": "sqlite",
            "code": code,
            "stock_info": info,
            "granularity": granularity,
            "metric_statistics": stats,
            "count": len(stats),
        }

    def query_asset_report_impacts(
        self, code: str, limit: int = 20, refresh_if_missing: bool = True
    ) -> Dict:
        info = self._ensure_stock_info(code, realtime=False)
        impacts = self.db.get_report_impacts(info["stock_id"], limit=limit if limit > 0 else None)

        if refresh_if_missing and not impacts:
            self._refresh_from_online(code, granularity="fs")
            impacts = self.db.get_report_impacts(info["stock_id"], limit=limit if limit > 0 else None)

        return {
            "source": "sqlite",
            "code": code,
            "stock_info": info,
            "report_impacts": impacts,
            "count": len(impacts),
        }

    def refresh_asset(self, code: str, granularity: str = "y10") -> Dict:
        result = self._refresh_from_online(code, granularity=granularity)
        info = self.db.get_stock_info(code)
        return {
            "source": "online+sqlite",
            "refresh": result,
            "stock_info": info,
        }

    def screen_undervalued_stocks(
        self,
        market: str = "cn",
        pe_percentile_max: float = 0.20,
        pb_percentile_max: float = 0.20,
        ps_percentile_max: float = 0.20,
        dyr_percentile_min: float = 0.80,
        page_size: int = 200,
        page_index: int = 0
    ) -> Dict:
        """
        筛选低估股票池（实时从线上获取）
        
        Args:
            market: 市场代码，"cn"为A股，"hk"为港股
            pe_percentile_max: PE历史分位上限（0-1，默认0.20表示20%）
            pb_percentile_max: PB历史分位上限（0-1，默认0.20表示20%）
            ps_percentile_max: PS历史分位上限（0-1，默认0.20表示20%）
            dyr_percentile_min: 股息率历史分位下限（0-1，默认0.80表示80%）
            page_size: 每页返回数量（默认200）
            page_index: 页码，从0开始
            
        Returns:
            筛选结果字典
        """
        spider = self._ensure_spider()
        
        result = spider.screen_undervalued_stocks(
            area_code=market,
            pe_percentile_max=pe_percentile_max,
            pb_percentile_max=pb_percentile_max,
            ps_percentile_max=ps_percentile_max,
            dyr_percentile_min=dyr_percentile_min,
            page_size=page_size,
            page_index=page_index
        )
        
        if not result:
            return {
                "ok": False,
                "error": "筛选请求失败，请检查网络或cookie状态",
                "market": market,
                "filter_params": {
                    "pe_percentile_max": pe_percentile_max,
                    "pb_percentile_max": pb_percentile_max,
                    "ps_percentile_max": ps_percentile_max,
                    "dyr_percentile_min": dyr_percentile_min
                }
            }
        
        return {
            "ok": True,
            "source": "online",
            "market": market,
            "market_name": "A股" if market == "cn" else "港股",
            "total": result.total,
            "page_index": page_index,
            "page_size": page_size,
            "count": len(result.stocks),
            "filter_params": result.filter_params,
            "stocks": [s.to_dict() for s in result.stocks]
        }

