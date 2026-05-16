"""Tushare 概念/行业归属（百度 concept_blocks 备用）。"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


def _to_ts_code(symbol: str) -> str:
    s = (symbol or "").upper().strip()
    if "." in s and s.endswith((".SH", ".SZ", ".BJ")):
        return s
    if s.startswith("SH"):
        return f"{s[2:]}.SH"
    if s.startswith("SZ"):
        return f"{s[2:]}.SZ"
    if s.startswith("BJ"):
        return f"{s[2:]}.BJ"
    if s.isdigit() and len(s) == 6:
        if s.startswith("6"):
            return f"{s}.SH"
        if s.startswith(("4", "8")):
            return f"{s}.BJ"
        return f"{s}.SZ"
    return s


def fetch_concept_blocks_tushare(
    symbol: str,
    tushare_fn: Callable[..., Optional[List[Dict[str, Any]]]],
) -> Optional[Dict[str, Any]]:
    """
    用 stock_basic.industry + concept_detail 组装 concept_blocks 结构。

    Args:
        symbol: SH600519 等
        tushare_fn: 通常为 FinanceDataSource.tushare
    """
    ts_code = _to_ts_code(symbol)
    if not ts_code or "." not in ts_code:
        return None

    result: Dict[str, Any] = {
        "industry": [],
        "concept": [],
        "region": [],
        "concept_tags": [],
        "source": "tushare",
    }

    basic = tushare_fn("stock_basic", ts_code=ts_code, fields="ts_code,name,industry")
    if basic:
        ind = (basic[0].get("industry") or "").strip()
        name = (basic[0].get("name") or "").strip()
        if ind:
            result["industry"].append({"name": ind, "change_pct": "", "desc": name})

    concepts = tushare_fn("concept_detail", ts_code=ts_code)
    if concepts:
        for row in concepts:
            cname = (row.get("concept_name") or row.get("name") or "").strip()
            if not cname:
                continue
            entry = {"name": cname, "change_pct": "", "desc": ""}
            result["concept"].append(entry)
            result["concept_tags"].append(cname)

    if not result["industry"] and not result["concept"]:
        return None
    return result
