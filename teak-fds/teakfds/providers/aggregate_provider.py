#!/usr/bin/env python3
"""
AggregateProvider — 原 AkShare 能力区的内部实现（巨潮/东财/同花顺 HTTP）。

路由名仍为历史兼容；**不依赖 akshare 包**。
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from teakfds.datasource_log import log_error
from teakfds.integrations.cninfo_rating import fetch_rating_forecast_cninfo
from teakfds.integrations.eastmoney_comment import fetch_institution_participation_em
from teakfds.integrations.eastmoney_forecast import fetch_profit_forecast_em
from teakfds.integrations.eastmoney_gsrl import fetch_company_events_em
from teakfds.integrations.eastmoney_industry import fetch_industry_board_summary
from teakfds.integrations.eastmoney_notice import fetch_notice_report
from teakfds.integrations.ths_forecast_lite import fetch_consensus_eps_ths
from teakfds.providers.base_provider import BaseProvider, ProviderCapabilities
from teakfds.models import ProviderStatus


def _fds_to_code(symbol: str) -> str:
    s = (symbol or "").upper().strip()
    if s.startswith(("SH", "SZ", "BJ")):
        return s[2:]
    if "." in s:
        return s.split(".")[0]
    return s


def _norm_date_yyyy_mm_dd(d: Optional[str]) -> Optional[str]:
    if not d:
        return None
    s = str(d).strip().replace("-", "")
    if len(s) == 8:
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return d


def _cninfo_announcements(
    symbol: str,
    category: str = "",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Optional[List[Dict]]:
    try:
        from teakfds.providers.cninfo_provider import get_cninfo_provider

        raw = get_cninfo_provider().announcement_list(
            symbol,
            category=category,
            start_date=_norm_date_yyyy_mm_dd(start_date),
            end_date=_norm_date_yyyy_mm_dd(end_date),
            page_size=50,
        )
        if not raw or not raw.get("announcements"):
            return None
        return [
            {
                "title": a.get("title"),
                "date": a.get("announcement_time"),
                "category": a.get("category"),
                "url": a.get("adjunct_url"),
                "sec_code": a.get("sec_code"),
                "source": "cninfo",
            }
            for a in raw["announcements"]
        ]
    except Exception as e:
        log_error(f"AggregateProvider._cninfo_announcements: {e}")
        return None


class AggregateProvider(BaseProvider):
    name = "aggregate"
    display_name = "Teak聚合(巨潮/东财/同花顺)"
    priority = 50

    capabilities = ProviderCapabilities(
        supports_report=True,
        supports_announcement=True,
        markets=["a_share"],
    )

    MIN_INTERVAL = 0.5

    def __init__(self):
        super().__init__()
        self._last_request_time = 0.0

    def is_available(self) -> bool:
        return True

    def get_status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            available=True,
            last_success=datetime.now().isoformat(),
        )

    def _wait_rate_limit(self) -> None:
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self.MIN_INTERVAL:
            time.sleep(self.MIN_INTERVAL - elapsed)
        self._last_request_time = time.time()

    def report_list(
        self, symbol: str, start_date: str = None, end_date: str = None
    ) -> Optional[List[Dict]]:
        return self.announcement_list(symbol, category="", start_date=start_date, end_date=end_date)

    def profit_forecast(self, symbol: str) -> Optional[List[Dict]]:
        self._wait_rate_limit()
        rows = fetch_profit_forecast_em(symbol)
        if rows:
            return rows
        return fetch_consensus_eps_ths(symbol)

    def rating_summary(self, symbol: str) -> Optional[List[Dict]]:
        self._wait_rate_limit()
        date = datetime.now().strftime("%Y%m%d")
        result = fetch_rating_forecast_cninfo(date)
        if not result:
            return None
        if symbol:
            code = _fds_to_code(symbol)
            filtered = [
                r
                for r in result
                if code in str(r.get("证券代码", "")) or code in str(r.values())
            ]
            return filtered if filtered else result
        return result

    def institution_recommend(self, symbol: str) -> Optional[Dict]:
        self._wait_rate_limit()
        result = fetch_institution_participation_em(symbol)
        return {"data": result, "symbol": symbol} if result else None

    def institution_participation(self, symbol: str) -> Optional[Dict]:
        return self.institution_recommend(symbol)

    def announcement_list(
        self,
        symbol: str,
        category: str = "",
        start_date: str = None,
        end_date: str = None,
    ) -> Optional[List[Dict]]:
        if not start_date:
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y%m%d")
        rows = _cninfo_announcements(symbol, category, start_date, end_date)
        if rows:
            return rows
        self._wait_rate_limit()
        return fetch_notice_report(
            category=category or "全部",
            date=end_date,
            security=_fds_to_code(symbol),
        )

    def announcement_market(self, date: str, category: str = "全部") -> Optional[List[Dict]]:
        self._wait_rate_limit()
        return fetch_notice_report(category=category, date=date)

    def company_events(self, date: str) -> Optional[List[Dict]]:
        self._wait_rate_limit()
        return fetch_company_events_em(date)

    def industry_comparison(self, top_n: int = 20) -> Optional[Dict[str, Any]]:
        self._wait_rate_limit()
        return fetch_industry_board_summary(top_n=top_n)

    def consensus_eps(self, symbol: str) -> Optional[List[Dict]]:
        self._wait_rate_limit()
        rows = fetch_consensus_eps_ths(symbol)
        if rows:
            return rows
        pf = fetch_profit_forecast_em(symbol)
        if not pf:
            return None
        return [
            {
                "year": str(r.get("year", "")),
                "count": int(r.get("count", 0) or 0),
                "min": r.get("min"),
                "mean": r.get("eps"),
                "max": r.get("max"),
            }
            for r in pf
            if r.get("year") or r.get("eps")
        ]


_aggregate_provider: Optional[AggregateProvider] = None


def get_aggregate_provider() -> AggregateProvider:
    global _aggregate_provider
    if _aggregate_provider is None:
        _aggregate_provider = AggregateProvider()
    return _aggregate_provider


# 历史路由键兼容（旧代码 get_akshare_provider）
def get_akshare_provider() -> AggregateProvider:
    return get_aggregate_provider()
