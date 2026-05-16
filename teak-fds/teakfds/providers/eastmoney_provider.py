#!/usr/bin/env python3
"""
EastmoneyProvider - 东财 datacenter 数据源

提供:
- 全市场龙虎榜 (RPT_DAILYBILLBOARD_DETAILSNEW)
- 研报列表 + PDF 下载链接 (reportapi.eastmoney.com)

免费无 key，不封 IP。
"""

import re
from typing import Optional, Dict, Any, List
from datetime import datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from teakfds.datasource_log import log_info, log_warn, log_error
from teakfds.providers.base_provider import BaseProvider, ProviderCapabilities
from teakfds.models import ProviderStatus


_EM_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_EM_REFERER = "https://data.eastmoney.com/"
_PDF_TPL = "https://pdf.dfcfw.com/pdf/H3_{info_code}_1.pdf"


def _strip_prefix(symbol: str) -> str:
    s = symbol.upper()
    for pfx in ("SH", "SZ", "BJ"):
        if s.startswith(pfx):
            return s[len(pfx):]
    if "." in s:
        return s.split(".")[0]
    return symbol


class EastmoneyProvider(BaseProvider):
    name = "eastmoney"
    display_name = "东财 Datacenter"
    priority = 10

    capabilities = ProviderCapabilities(
        supports_report=True,
        markets=["a_share"],
    )

    def is_available(self) -> bool:
        return True

    def get_status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            available=True,
            last_success=datetime.now().isoformat(),
        )

    # ========== 全市场龙虎榜 ==========

    def daily_dragon_tiger(self, trade_date: str = None, min_net_buy: float = None) -> Optional[Dict]:
        """全市场龙虎榜。

        Args:
            trade_date: YYYY-MM-DD（默认当日）
            min_net_buy: 净买入下限（万元）

        Returns:
            {date, total_records, stocks: [{code, name, reason, close, change_pct,
             net_buy_wan, buy_wan, sell_wan, turnover_pct}]}
        """
        import requests

        if trade_date is None:
            trade_date = datetime.now().strftime("%Y-%m-%d")

        url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
        params = {
            "reportName": "RPT_DAILYBILLBOARD_DETAILSNEW",
            "columns": "ALL",
            "filter": f"(TRADE_DATE>='{trade_date}')(TRADE_DATE<='{trade_date}')",
            "pageNumber": "1",
            "pageSize": "500",
            "sortTypes": "-1",
            "sortColumns": "BILLBOARD_NET_AMT",
            "source": "WEB",
            "client": "WEB",
        }
        headers = {"User-Agent": _EM_UA, "Referer": _EM_REFERER}

        try:
            r = requests.get(url, params=params, headers=headers, timeout=15)
            d = r.json()
        except Exception as e:
            log_error(f"eastmoney daily_dragon_tiger error: {e}")
            return None

        if not d.get("success") or not d.get("result") or not d["result"].get("data"):
            return {"date": trade_date, "total_records": 0, "stocks": [],
                    "note": "无数据（非交易日或盘后未更新）"}

        data = d["result"]["data"]
        actual_date = data[0].get("TRADE_DATE", "")[:10] if data else trade_date

        stocks = []
        for row in data:
            net_buy = (row.get("BILLBOARD_NET_AMT") or 0) / 10000
            if min_net_buy is not None and net_buy < min_net_buy:
                continue
            stocks.append({
                "code": row.get("SECURITY_CODE", ""),
                "name": row.get("SECURITY_NAME_ABBR", ""),
                "reason": row.get("EXPLANATION", ""),
                "close": row.get("CLOSE_PRICE") or 0,
                "change_pct": round(float(row.get("CHANGE_RATE") or 0), 2),
                "net_buy_wan": round(net_buy, 1),
                "buy_wan": round((row.get("BILLBOARD_BUY_AMT") or 0) / 10000, 1),
                "sell_wan": round((row.get("BILLBOARD_SELL_AMT") or 0) / 10000, 1),
                "turnover_pct": round(float(row.get("TURNOVERRATE") or 0), 2),
            })

        return {"date": actual_date, "total_records": len(stocks), "stocks": stocks}

    # ========== 研报列表 + PDF ==========

    def report_list(self, symbol: str, max_pages: int = 3) -> Optional[List[Dict]]:
        """东财研报列表（reportapi）。"""
        import requests
        import time as _time

        code = _strip_prefix(symbol)
        session = requests.Session()
        session.headers.update({"User-Agent": _EM_UA, "Referer": _EM_REFERER})

        all_records: List[Dict] = []
        api_url = "https://reportapi.eastmoney.com/report/list"

        for page in range(1, max_pages + 1):
            params = {
                "industryCode": "*", "pageSize": "100", "industry": "*",
                "rating": "*", "ratingChange": "*",
                "beginTime": "2000-01-01", "endTime": "2030-01-01",
                "pageNo": str(page), "fields": "", "qType": "0",
                "orgCode": "", "code": code, "rcode": "",
                "p": str(page), "pageNum": str(page), "pageNumber": str(page),
            }
            try:
                r = session.get(api_url, params=params, timeout=30)
                d = r.json()
            except Exception as e:
                log_error(f"eastmoney report_list page {page} error: {e}")
                break

            rows = d.get("data") or []
            if not rows:
                break

            for row in rows:
                info_code = row.get("infoCode", "")
                all_records.append({
                    "title": row.get("title", ""),
                    "publish_date": (row.get("publishDate") or "")[:10],
                    "org_name": row.get("orgSName", ""),
                    "info_code": info_code,
                    "pdf_url": _PDF_TPL.format(info_code=info_code) if info_code else None,
                    "eps_this_year": row.get("predictThisYearEps"),
                    "eps_next_year": row.get("predictNextYearEps"),
                    "eps_next2_year": row.get("predictNextTwoYearEps"),
                    "rating": row.get("emRatingName", ""),
                    "industry": row.get("indvInduName", ""),
                })

            if page >= (d.get("TotalPage", 1) or 1):
                break
            _time.sleep(0.3)

        return all_records if all_records else None


# 单例
_instance: Optional[EastmoneyProvider] = None


def get_eastmoney_provider() -> EastmoneyProvider:
    global _instance
    if _instance is None:
        _instance = EastmoneyProvider()
    return _instance
