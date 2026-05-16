"""东财股市日历 — 公司动态。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from teakfds.integrations.eastmoney_datacenter import em_get


def _date_dash(yyyymmdd: str) -> str:
    s = (yyyymmdd or "").replace("-", "")
    if len(s) == 8:
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return yyyymmdd


def fetch_company_events_em(date: str) -> Optional[List[Dict[str, Any]]]:
    d = _date_dash(date)
    rows = em_get(
        report_name="RPT_ORGOP_ALL",
        columns="SECURITY_CODE,SECUCODE,SECURITY_NAME_ABBR,EVENT_TYPE,EVENT_CONTENT,TRADE_DATE",
        filter_expr=f"(TRADE_DATE='{d}')",
        page_size=5000,
        sort_columns="SECURITY_CODE",
        sort_types="1",
    )
    if not rows:
        return None
    out: List[Dict[str, Any]] = []
    for i, r in enumerate(rows, 1):
        out.append(
            {
                "序号": i,
                "代码": r.get("SECURITY_CODE"),
                "简称": r.get("SECURITY_NAME_ABBR"),
                "事件类型": r.get("EVENT_TYPE"),
                "具体事项": r.get("EVENT_CONTENT"),
                "交易日": r.get("TRADE_DATE"),
            }
        )
    return out
