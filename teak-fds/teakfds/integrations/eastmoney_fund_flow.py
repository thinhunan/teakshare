"""东财个股日级资金流向（替代失效的百度 fundsortlist）。"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import requests

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}


def _market_secid(symbol: str) -> str:
    s = (symbol or "").upper().strip()
    if s.startswith("SH"):
        return f"1.{s[2:]}"
    if s.startswith("SZ"):
        return f"0.{s[2:]}"
    if s.startswith("BJ"):
        return f"0.{s[2:]}"
    if "." in s:
        code, ex = s.split(".", 1)
        return f"{'1' if ex == 'SH' else '0'}.{code}"
    return f"1.{s}"


def fetch_stock_fund_flow_em(symbol: str, days: int = 20) -> Optional[List[Dict[str, Any]]]:
    """
    东财 push2his 日级资金流。

    Returns list[dict] 含 date, close, change_pct, main_net, superNetIn, largeNetIn 等。
    """
    secid = _market_secid(symbol)
    url = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
    params = {
        "lmt": "0",
        "klt": "101",
        "secid": secid,
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
        "ut": "b2884a393a59ad64002292a3e90d46a5",
        "_": int(time.time() * 1000),
    }
    try:
        r = requests.get(url, params=params, headers=_HEADERS, timeout=15)
        data = r.json()
    except Exception:
        return None

    klines = (data.get("data") or {}).get("klines") or []
    if not klines:
        return None

    out: List[Dict[str, Any]] = []
    for line in klines:
        parts = str(line).split(",")
        if len(parts) < 12:
            continue
        try:
            main_net = float(parts[1]) if parts[1] else 0.0
        except (TypeError, ValueError):
            main_net = 0.0
        out.append(
            {
                "date": parts[0],
                "trade_date": parts[0].replace("-", ""),
                "close": parts[11] if len(parts) > 11 else None,
                "change_pct": parts[12] if len(parts) > 12 else None,
                "main_net": main_net,
                "mainIn": main_net,
                "net_mf_amount": main_net,
                "superNetIn": parts[5] if len(parts) > 5 else None,
                "largeNetIn": parts[7] if len(parts) > 7 else None,
                "mediumNetIn": parts[9] if len(parts) > 9 else None,
                "littleNetIn": parts[3] if len(parts) > 3 else None,
                "source": "eastmoney",
            }
        )

    if days and len(out) > days:
        out = out[-days:]
    return out or None
