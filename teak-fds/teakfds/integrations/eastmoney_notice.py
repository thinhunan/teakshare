"""东财公告大全 API（np-anotice-stock）。"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import requests

_NOTICE_URL = "https://np-anotice-stock.eastmoney.com/api/security/ann"
_REPORT_MAP = {
    "全部": "0",
    "财务报告": "1",
    "融资公告": "2",
    "风险提示": "3",
    "信息变更": "4",
    "重大事项": "5",
    "资产重组": "6",
    "持股变动": "7",
}


def _date_dash(yyyymmdd: str) -> str:
    s = (yyyymmdd or "").replace("-", "")
    if len(s) == 8:
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return yyyymmdd


def fetch_notice_report(
    category: str = "全部",
    date: str = "",
    security: Optional[str] = None,
) -> Optional[List[Dict[str, Any]]]:
    """全市场或单股公告（东财）。"""
    cat = category if category in _REPORT_MAP else "全部"
    begin = _date_dash(date) if date else None
    params: Dict[str, str] = {
        "sr": "-1",
        "page_size": "100",
        "page_index": "1",
        "ann_type": "A",
        "client_source": "web",
        "f_node": _REPORT_MAP[cat],
        "s_node": "0",
    }
    if security:
        params["stock_list"] = security
    if begin:
        params["begin_time"] = begin
        params["end_time"] = begin

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://data.eastmoney.com/notices/",
    }
    try:
        r = requests.get(_NOTICE_URL, params=params, headers=headers, timeout=20)
        r.raise_for_status()
        data_json = r.json()
    except Exception:
        return None

    total = int((data_json.get("data") or {}).get("total_hits") or 0)
    total_page = max(1, math.ceil(total / 100))
    out: List[Dict[str, Any]] = []

    for page in range(1, total_page + 1):
        params["page_index"] = str(page)
        try:
            r = requests.get(_NOTICE_URL, params=params, headers=headers, timeout=20)
            chunk = (r.json().get("data") or {}).get("list") or []
        except Exception:
            break
        for item in chunk:
            code = name = ""
            codes = item.get("codes") or []
            if codes:
                c0 = codes[0]
                if isinstance(c0, dict):
                    code = c0.get("stock_code") or c0.get("code") or ""
                    name = c0.get("short_name") or ""
                else:
                    code = str(c0)
            cols = item.get("columns") or []
            col_name = cols[0].get("column_name") if cols else ""
            art = item.get("art_code") or ""
            url = f"https://data.eastmoney.com/notices/detail/{code}/{art}.html" if code and art else ""
            out.append(
                {
                    "代码": code,
                    "名称": name,
                    "公告标题": item.get("title"),
                    "公告类型": col_name,
                    "公告日期": item.get("notice_date"),
                    "网址": url,
                }
            )
        if len(chunk) < 100:
            break
    return out or None
