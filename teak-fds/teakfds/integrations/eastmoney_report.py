"""东财研报列表 → 机构评级字段（reportapi）。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _strip_prefix(symbol: str) -> str:
    s = (symbol or "").upper().strip()
    for pfx in ("SH", "SZ", "BJ"):
        if s.startswith(pfx):
            return s[len(pfx):]
    if "." in s:
        return s.split(".")[0]
    return s


def fetch_stock_report_ratings(symbol: str, max_pages: int = 2) -> Optional[List[Dict[str, Any]]]:
    """个股研报列表，含机构评级（东财 reportapi）。"""
    from teakfds.providers.eastmoney_provider import get_eastmoney_provider

    rows = get_eastmoney_provider().report_list(symbol, max_pages=max_pages)
    if not rows:
        return None
    code = _strip_prefix(symbol)
    out: List[Dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "title": row.get("title"),
                "证券代码": code,
                "证券简称": row.get("name") or "",
                "发布日期": row.get("publish_date"),
                "研究机构简称": row.get("org_name"),
                "投资评级": row.get("rating"),
                "行业": row.get("industry"),
                "pdf_url": row.get("pdf_url"),
                "eps_this_year": row.get("eps_this_year"),
                "eps_next_year": row.get("eps_next_year"),
                "source": "eastmoney",
            }
        )
    return out
