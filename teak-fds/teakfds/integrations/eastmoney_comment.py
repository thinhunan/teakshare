"""东财千股千评 — 机构参与度。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from teakfds.integrations.eastmoney_datacenter import em_get


def _fds_to_code(symbol: str) -> str:
    s = (symbol or "").upper().strip()
    if s.startswith(("SH", "SZ", "BJ")):
        return s[2:]
    if "." in s:
        return s.split(".")[0]
    return s


def fetch_institution_participation_em(symbol: str) -> Optional[List[Dict[str, Any]]]:
    code = _fds_to_code(symbol)
    rows = em_get(
        report_name="RPT_DMSK_TS_STOCKEVALUATE",
        filter_expr=f'(SECURITY_CODE="{code}")',
        sort_columns="TRADE_DATE",
        sort_types="-1",
        page_size=120,
    )
    if not rows:
        return None
    out: List[Dict[str, Any]] = []
    for r in rows:
        part = r.get("ORG_PARTICIPATE")
        try:
            part_pct = float(part) * 100 if part is not None else None
        except (TypeError, ValueError):
            part_pct = None
        out.append(
            {
                "trade_date": r.get("TRADE_DATE"),
                "机构参与度": part_pct,
                "participation_pct": part_pct,
            }
        )
    out.sort(key=lambda x: str(x.get("trade_date") or ""))
    return out
