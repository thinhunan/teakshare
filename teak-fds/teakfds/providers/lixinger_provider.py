#!/usr/bin/env python3
"""
LixingerProvider - 理杏仁估值数据Provider (完整版)
P0级别 - 估值数据主源

依赖：仅 `teakfds/providers/lixinger/` 下 `settings.json` 与 `cookie.txt`；爬虫内置失效后自动模拟登录更新 Cookie。
若接口持续不可用，视为实现缺陷（非「缺第三方 Token」场景）。

完整拷贝自 lixinger-data-query skill，包含：
- 自动使用 cookie
- Cookie 失效自动登录
- 数据缓存到 SQLite
"""

from pathlib import Path
from typing import List, Optional, Dict, Any, Literal, Tuple

from datetime import datetime

from teakfds.providers.base_provider import BaseProvider, ProviderCapabilities
from teakfds.models import ValuationData, ProviderStatus

# 导入完整版理杏仁爬虫
from .lixinger import LixingerSpider
from .lixinger.lixinger_spider import UndervaluedScreenerResult, MetricStatistics


class LixingerProvider(BaseProvider):
    """
    理杏仁数据提供商 - P0估值主源 (完整版)
    
    使用完整拷贝的lixinger-data-query代码，支持：
    - 自动使用cookie
    - Cookie失效自动登录
    - 数据缓存到SQLite
    """
    
    name = "lixinger"
    display_name = "理杏仁"
    priority = 90  # P0级别
    
    capabilities = ProviderCapabilities(
        supports_valuation=True,
        supports_financial=False,
        markets=['a_share', 'hk']
    )
    
    # 默认数据目录
    DEFAULT_DATA_DIR = Path.home() / 'agents_documents' / 'lixinger_crawl'

    @staticmethod
    def _resolve_lixinger_paths() -> Tuple[Path, Path]:
        """仅使用本包内 ``teakfds/providers/lixinger/``（不依赖 finance-data-source 等外部目录）。"""
        lixinger_dir = Path(__file__).parent / 'lixinger'
        settings_path = lixinger_dir / 'settings.json'
        if not settings_path.is_file():
            example = lixinger_dir / 'settings.example.json'
            if example.is_file():
                raise FileNotFoundError(
                    f"缺少 {settings_path}；请从 settings.example.json 复制并填写账号，"
                    "见 references/config.md"
                )
        return settings_path, lixinger_dir / 'cookie.txt'

    def _reset_spider(self) -> None:
        self._spider = None
        self._available = None
        self._last_error = None
    
    def __init__(self):
        super().__init__()
        self._spider = None
        self._available = None
        self._last_error = None
    
    def _ensure_spider(self) -> Optional[LixingerSpider]:
        """确保spider已初始化"""
        if self._spider is not None:
            return self._spider
        
        try:
            settings_path, cookie_path = self._resolve_lixinger_paths()
            db_path = self.DEFAULT_DATA_DIR / 'db' / 'lixinger.db'
            
            # 确保数据目录存在
            db_path.parent.mkdir(parents=True, exist_ok=True)
            
            self._spider = LixingerSpider(
                settings_path=str(settings_path),
                cookie_path=str(cookie_path),
                db_path=str(db_path),
                auto_save=False,
                force_use_cookie=True  # 强制使用现有cookie，失败时自动登录
            )
            self._available = True
            return self._spider
            
        except Exception as e:
            self._last_error = str(e)
            self._available = False
            return None
    
    def is_available(self) -> bool:
        """检查是否可用"""
        if self._available is not None:
            return self._available
        
        spider = self._ensure_spider()
        return spider is not None
    
    def get_status(self) -> ProviderStatus:
        """获取Provider状态"""
        available = self.is_available()
        return ProviderStatus(
            name=self.name,
            available=available,
            last_success=datetime.now().isoformat() if available else None,
            last_failure=self._last_error if self._last_error else None,
        )
    
    def _normalize_code(self, symbol: str) -> str:
        """标准化为理杏仁 API 使用的纯数字 stockCode（A 股 6 位、港股 5 位等）。"""
        s = (symbol or "").strip().upper()
        if not s:
            return s
        if s.endswith('.HK'):
            core = s[:-3].strip()
            return core[2:] if core.startswith('HK') else core.replace('.', '')
        if '.' in s:
            left, right = s.split('.', 1)
            if right in ('SH', 'SZ', 'SS', 'BJ'):
                return left
            if right == 'HK':
                return left[2:] if left.startswith('HK') else left
        s = s.replace('.', '')
        if s.startswith('HK') and len(s) > 5:
            return s[2:]
        if s.startswith(('SH', 'SZ', 'BJ')):
            return s[2:]
        return s
    
    def valuation(self, symbol: str) -> Optional[ValuationData]:
        """
        获取估值数据 - 统一接口
        
        Args:
            symbol: 股票代码 (如 'SH688106', '688106.SH', '688106')
        
        Returns:
            ValuationData 或 None
        """
        if not self.is_available():
            return None
        
        try:
            spider = self._ensure_spider()
            if spider is None:
                return None
            
            # 标准化代码
            code = self._normalize_code(symbol)
            
            # 使用完整版爬虫获取数据
            data = spider.get_comprehensive_data(
                code,
                granularity='y10',  # 10年数据
                save_to_db=False,
                smart_granularity=False
            )
            
            if not data or not data.stock_info:
                return None
            
            info = data.stock_info

            # 从 daily_data 获取最新市值（单位转换为亿元）
            market_cap = None
            if data.daily_data:
                latest = data.daily_data[0]
                if latest.mc:
                    market_cap = latest.mc / 1e8  # 转换为亿元

            # 转换为统一的 ValuationData
            return ValuationData(
                symbol=symbol,
                name=info.name,
                pe_ttm=info.pe_ttm if info.pe_ttm else None,
                pe_lyr=info.d_pe_ttm if info.d_pe_ttm else None,  # 扣非PE
                pb=info.pb if info.pb else None,
                ps_ttm=info.ps_ttm if info.ps_ttm else None,
                dividend_yield=(
                    (info.dividend_yield / 100.0)
                    if info.dividend_yield and abs(info.dividend_yield) > 0.2
                    else info.dividend_yield
                ) if info.dividend_yield else None,
                market_cap=market_cap,
                source='lixinger',
                update_time=datetime.now().isoformat()
            )
            
        except Exception as e:
            self._last_error = str(e)
            print(f"LixingerProvider.valuation error: {e}")
            return None
    
    def get_comprehensive_data(self, symbol: str, granularity: str = 'y10'):
        """
        获取完整数据（包括历史、统计、财报影响等）
        
        Args:
            symbol: 股票代码
            granularity: 时间粒度 (y1/y3/y5/y10/fs)
        
        Returns:
            ComprehensiveData 或 None
        """
        if not self.is_available():
            return None
        
        try:
            spider = self._ensure_spider()
            if spider is None:
                return None
            
            code = self._normalize_code(symbol)
            return spider.get_comprehensive_data(code, granularity=granularity)
            
        except Exception as e:
            self._last_error = str(e)
            print(f"LixingerProvider.get_comprehensive_data error: {e}")
            return None
    
    def screen_undervalued_stocks(
        self,
        area_code: Literal["cn", "hk"] = "cn",
        pe_percentile_max: float = 0.20,
        pb_percentile_max: float = 0.20,
        ps_percentile_max: float = 0.20,
        dyr_percentile_min: float = 0.80,
        page_size: int = 200,
        page_index: int = 0,
    ) -> Optional[UndervaluedScreenerResult]:
        """
        理杏仁 company screener：按历史估值分位筛选 A 股 / 港股低估池。

        底层: POST https://www.lixinger.com/api/company/screener
        """
        if not self.is_available():
            return None
        spider = self._ensure_spider()
        if spider is None:
            return None
        try:
            return spider.screen_undervalued_stocks(
                area_code=area_code,
                pe_percentile_max=pe_percentile_max,
                pb_percentile_max=pb_percentile_max,
                ps_percentile_max=ps_percentile_max,
                dyr_percentile_min=dyr_percentile_min,
                page_size=page_size,
                page_index=page_index,
            )
        except Exception as e:
            self._last_error = str(e)
            print(f"LixingerProvider.screen_undervalued_stocks error: {e}")
            return None

    @staticmethod
    def _granularity_for_years(years: int) -> str:
        if years and int(years) <= 5:
            return "y5"
        return "y10"

    @staticmethod
    def _stats_to_percentile_dict(
        stats: Optional[MetricStatistics],
        current: Optional[float],
    ) -> Dict[str, Any]:
        """
        将 ``get-price-metrics-chart-info`` 解析得到的 MetricStatistics 转为统一字典。
        字段与理杏仁 ``allStatisticsData`` 一致：当前值、历史分位(cvpos)、q2v/q5v/q8v、min/max/avg。
        """
        if not stats:
            return {
                "current": current,
                "percentile": None,
                "percentile_20": None,
                "percentile_50": None,
                "percentile_80": None,
                "max": None,
                "min": None,
                "avg": None,
            }
        return {
            "current": current,
            "percentile": stats.current_percentile,
            "percentile_20": stats.percentile_20,
            "percentile_50": stats.percentile_50,
            "percentile_80": stats.percentile_80,
            "max": stats.max_value,
            "min": stats.min_value,
            "avg": stats.avg_value,
        }

    @staticmethod
    def _normalize_price_metric(metric: Optional[str]) -> Optional[str]:
        """将别名规范为 allStatisticsData 使用的键：pe_ttm / pb / ps_ttm / dyr。"""
        if not metric or not str(metric).strip():
            return "pe_ttm"
        key = str(metric).lower().strip()
        aliases = {
            "pe": "pe_ttm",
            "ps": "ps_ttm",
            "dividend_yield": "dyr",
        }
        key = aliases.get(key, key)
        if key in ("pe_ttm", "pb", "ps_ttm", "dyr"):
            return key
        return None

    def _metric_to_stats_and_current(
        self, canonical: str, data: Any, info: Any
    ) -> Tuple[Optional[MetricStatistics], Optional[float]]:
        if canonical == "pe_ttm":
            return data.pe_stats, getattr(info, "pe_ttm", None)
        if canonical == "pb":
            return data.pb_stats, getattr(info, "pb", None)
        if canonical == "ps_ttm":
            return data.ps_stats, getattr(info, "ps_ttm", None)
        if canonical == "dyr":
            return data.dyr_stats, getattr(info, "dividend_yield", None)
        return None, None

    def get_percentile(self, symbol: str, metric: str = "pe", years: int = 10) -> Optional[Dict]:
        """
        获取价格指标历史分位（理杏仁 ``/api/company/price-metrics/get-price-metrics-chart-info``）。

        Args:
            symbol: 股票代码 (如 'SH600519', '688106.SH', '00700.HK')
            metric:
                - ``pe`` / ``pe_ttm``: PE-TTM（对应接口 pe_ttm）
                - ``pb``: PB
                - ``ps`` / ``ps_ttm``: PS-TTM
                - ``dyr``: 股息率
            years: 5 或 10（对应请求粒度 y5 / y10）

        Returns:
            ``current``, ``percentile``(历史分位 0-100), ``percentile_20``/``50``/``80``,
            ``max``, ``min``, ``avg``；无统计对象时各分位字段可为 None。
        """
        try:
            spider = self._ensure_spider()
            if spider is None:
                self._reset_spider()
                spider = self._ensure_spider()
            if spider is None:
                return None

            code = self._normalize_code(symbol)
            granularity = self._granularity_for_years(years)
            data = spider.get_comprehensive_data(
                code,
                granularity=granularity,
                save_to_db=False,
                smart_granularity=False,
            )

            if not data or not data.stock_info:
                return None

            info = data.stock_info
            canon = self._normalize_price_metric(metric)
            if canon is None:
                return None
            stats, current = self._metric_to_stats_and_current(canon, data, info)
            return self._stats_to_percentile_dict(stats, current)

        except Exception as e:
            self._last_error = str(e)
            print(f"LixingerProvider.get_percentile error: {e}")
            return None

    def get_valuation_percentiles_bundle(
        self, symbol: str, years: int = 10
    ) -> Optional[Dict[str, Any]]:
        """
        一次请求返回 PE-TTM / PB / PS-TTM / 股息率 四套分位数据（底层同一次 comprehensive 拉取）。

        Returns:
            ``pe_ttm``, ``pb``, ``ps_ttm``, ``dyr`` 各为与 ``get_percentile`` 相同结构的 dict；
            另含 ``granularity``、``symbol``。
        """
        try:
            spider = self._ensure_spider()
            if spider is None:
                self._reset_spider()
                spider = self._ensure_spider()
            if spider is None:
                return None
            code = self._normalize_code(symbol)
            granularity = self._granularity_for_years(years)
            data = spider.get_comprehensive_data(
                code,
                granularity=granularity,
                save_to_db=False,
                smart_granularity=False,
            )
            if not data or not data.stock_info:
                return None
            info = data.stock_info
            return {
                "symbol": symbol,
                "granularity": granularity,
                "pe_ttm": self._stats_to_percentile_dict(data.pe_stats, info.pe_ttm),
                "pb": self._stats_to_percentile_dict(data.pb_stats, info.pb),
                "ps_ttm": self._stats_to_percentile_dict(data.ps_stats, info.ps_ttm),
                "dyr": self._stats_to_percentile_dict(data.dyr_stats, info.dividend_yield),
            }
        except Exception as e:
            self._last_error = str(e)
            print(f"LixingerProvider.get_valuation_percentiles_bundle error: {e}")
            return None


# 全局实例
lixinger_provider: Optional[LixingerProvider] = None


def get_lixinger_provider() -> LixingerProvider:
    """获取全局LixingerProvider"""
    global lixinger_provider
    if lixinger_provider is None:
        lixinger_provider = LixingerProvider()
    return lixinger_provider


if __name__ == '__main__':
    print("Testing LixingerProvider (完整版)...")
    
    provider = get_lixinger_provider()
    print(f"Available: {provider.is_available()}")
    
    if provider.is_available():
        # 测试估值查询
        val = provider.valuation('SH600519')
        if val:
            print(f"SH600519: {val.name}")
            print(f"  PE-TTM: {val.pe_ttm}")
            print(f"  PB: {val.pb}")
            print(f"  来源: {val.source}")
        else:
            print("查询失败")
    
    print("\nTest done!")
