"""东财盈利预测（RPT_WEB_RESPREDICT）。"""

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


def fetch_profit_forecast_em(symbol: str) -> Optional[List[Dict[str, Any]]]:
    """
  个股盈利预测（东财 datacenter）。

  Returns list[dict] 含 code/name/report_count 及各年 eps 字段。
    """
    code = _fds_to_code(symbol)
    rows = em_get(
        report_name="RPT_WEB_RESPREDICT",
        columns="WEB_RESPREDICT",
        filter_expr=f'(SECURITY_CODE="{code}")',
        page_size=50,
        sort_columns="RATING_ORG_NUM",
        sort_types="-1",
    )
    if not rows:
        return None

    out: List[Dict[str, Any]] = []
    for r in rows:
        item: Dict[str, Any] = {
            "code": r.get("SECURITY_CODE") or code,
            "name": r.get("SECURITY_NAME_ABBR"),
            "report_count": r.get("RATING_ORG_NUM"),
            "buy_rating": r.get("RATING_BUY_NUM"),
            "overweight_rating": r.get("RATING_ADD_NUM"),
            "neutral_rating": r.get("RATING_NEUTRAL_NUM"),
            "underweight_rating": r.get("RATING_REDUCE_NUM"),
            "sell_rating": r.get("RATING_SELL_NUM"),
        }
        out.append(item)

    if not out:
        return None

    forecasts: List[Dict[str, Any]] = []
    row = rows[0]
    count = int(row.get("RATING_ORG_NUM") or 0)
    for i in range(1, 5):
        year = row.get(f"YEAR{i}")
        eps = row.get(f"EPS{i}")
        if year is None or eps is None:
            continue
        try:
            forecasts.append(
                {"year": str(year), "eps": float(eps), "count": count}
            )
        except (TypeError, ValueError):
            continue
    return forecasts or out
