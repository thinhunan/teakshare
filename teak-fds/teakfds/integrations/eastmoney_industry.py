"""东财行业板块一览；push2 不可用时回退 Tushare moneyflow_ind_ths。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

import requests

from teakfds.datasource_log import log_warn

_PUSH_HOSTS = (
    "17.push2.eastmoney.com",
    "push2.eastmoney.com",
    "82.push2.eastmoney.com",
    "63.push2.eastmoney.com",
)
_PUSH_PATH = "/api/qt/clist/get"
_FIELDS = (
    "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21,"
    "f23,f24,f25,f26,f22,f33,f11,f62,f128,f136,f115,f152,f124,f107,f104,f105,"
    "f140,f141,f207,f208,f209,f222"
)
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://quote.eastmoney.com/",
}


def _fetch_page(pn: int, pz: int = 100) -> List[Dict[str, Any]]:
    params = {
        "pn": str(pn),
        "pz": str(pz),
        "po": "1",
        "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2",
        "invt": "2",
        "fid": "f3",
        "fs": "m:90 t:2 f:!50",
        "fields": _FIELDS,
    }
    last_err: Optional[Exception] = None
    for host in _PUSH_HOSTS:
        url = f"https://{host}{_PUSH_PATH}"
        try:
            r = requests.get(url, params=params, headers=_HEADERS, timeout=20)
            r.raise_for_status()
            data = r.json().get("data") or {}
            diff = data.get("diff") or []
            if isinstance(diff, dict):
                diff = list(diff.values())
            return list(diff)
        except Exception as e:
            last_err = e
            continue
    if last_err:
        log_warn(f"eastmoney industry push2 all hosts failed: {last_err}")
    return []


def _parse_push2_rows(all_rows: List[Dict[str, Any]], top_n: int) -> Dict[str, Any]:
    parsed: List[Dict[str, Any]] = []
    for i, row in enumerate(all_rows):
        try:
            change = float(row.get("f3") or 0)
        except (TypeError, ValueError):
            change = 0.0
        try:
            turnover = float(row.get("f6") or 0)
        except (TypeError, ValueError):
            turnover = 0.0
        parsed.append(
            {
                "rank": i + 1,
                "name": row.get("f14") or "",
                "code": row.get("f12") or "",
                "change_pct": change,
                "turnover_yi": turnover,
                "net_inflow_yi": row.get("f62"),
                "up_count": row.get("f104"),
                "down_count": row.get("f105"),
                "leader": row.get("f128") or "",
                "source": "eastmoney",
            }
        )
    parsed.sort(key=lambda x: x.get("change_pct") or 0, reverse=True)
    for i, row in enumerate(parsed, 1):
        row["rank"] = i
    return {
        "top": parsed[:top_n],
        "bottom": parsed[-top_n:] if len(parsed) > top_n else parsed,
        "total": len(parsed),
        "source": "eastmoney",
    }


def fetch_industry_board_summary_tushare(
    top_n: int = 20,
    tushare_fn: Optional[Callable[..., Optional[List[Dict[str, Any]]]]] = None,
) -> Optional[Dict[str, Any]]:
    """同花顺行业板块资金流/涨跌（moneyflow_ind_ths）。"""
    if tushare_fn is None:
        from teakfds.providers.tushare_provider import tushare_provider

        if not tushare_provider.is_available():
            return None

        def _fn(api: str, **kwargs):
            return tushare_provider.pro_call(api, **kwargs)

        tushare_fn = _fn

    rows: Optional[List[Dict[str, Any]]] = None
    trade_date_used: Optional[str] = None
    for i in range(12):
        d = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
        if datetime.strptime(d, "%Y%m%d").weekday() >= 5:
            continue
        rows = tushare_fn("moneyflow_ind_ths", trade_date=d)
        if rows:
            trade_date_used = d
            break
    if not rows:
        return None

    parsed: List[Dict[str, Any]] = []
    for row in rows:
        try:
            change = float(row.get("pct_change") or 0)
        except (TypeError, ValueError):
            change = 0.0
        try:
            net_yi = float(row.get("net_amount") or 0)
        except (TypeError, ValueError):
            net_yi = None
        parsed.append(
            {
                "name": row.get("industry") or "",
                "code": row.get("ts_code") or "",
                "change_pct": change,
                "turnover_yi": None,
                "net_inflow_yi": net_yi,
                "up_count": row.get("company_num"),
                "down_count": None,
                "leader": row.get("lead_stock") or "",
                "source": "tushare",
            }
        )
    parsed.sort(key=lambda x: x.get("change_pct") or 0, reverse=True)
    for i, row in enumerate(parsed, 1):
        row["rank"] = i
    return {
        "top": parsed[:top_n],
        "bottom": parsed[-top_n:] if len(parsed) > top_n else parsed,
        "total": len(parsed),
        "trade_date": trade_date_used,
        "source": "tushare",
    }


def fetch_industry_board_summary(top_n: int = 20) -> Optional[Dict[str, Any]]:
    """行业涨跌幅排名：东财 push2 → Tushare moneyflow_ind_ths。"""
    all_rows: List[Dict[str, Any]] = []
    pn = 1
    while pn <= 30:
        chunk = _fetch_page(pn)
        if not chunk:
            break
        all_rows.extend(chunk)
        if len(chunk) < 100:
            break
        pn += 1

    if all_rows:
        return _parse_push2_rows(all_rows, top_n)

    return fetch_industry_board_summary_tushare(top_n=top_n)
