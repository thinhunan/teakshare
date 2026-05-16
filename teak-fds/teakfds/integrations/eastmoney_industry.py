"""东财行业板块一览（替代同花顺行业汇总，无 py_mini_racer）。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests

_PUSH_URL = "https://17.push2.eastmoney.com/api/qt/clist/get"
_FIELDS = (
    "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21,"
    "f23,f24,f25,f26,f22,f33,f11,f62,f128,f136,f115,f152,f124,f107,f104,f105,"
    "f140,f141,f207,f208,f209,f222"
)


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
    r = requests.get(_PUSH_URL, params=params, timeout=20)
    r.raise_for_status()
    data = r.json().get("data") or {}
    diff = data.get("diff") or []
    if isinstance(diff, dict):
        diff = list(diff.values())
    return list(diff)


def fetch_industry_board_summary(top_n: int = 20) -> Optional[Dict[str, Any]]:
    """行业涨跌幅排名（东财 push2）。"""
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

    if not all_rows:
        return {"top": [], "bottom": [], "total": 0}

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
            }
        )

    parsed.sort(key=lambda x: x.get("change_pct") or 0, reverse=True)
    for i, row in enumerate(parsed, 1):
        row["rank"] = i

    return {
        "top": parsed[:top_n],
        "bottom": parsed[-top_n:] if len(parsed) > top_n else parsed,
        "total": len(parsed),
    }
