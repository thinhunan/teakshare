"""门面 API 语义契约：返回字段与数值合理性检查。"""

from __future__ import annotations

from dataclasses import is_dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

CheckFn = Callable[[Any], Tuple[bool, str]]


def _list_dicts(data: Any) -> List[Dict[str, Any]]:
    if not isinstance(data, list):
        return []
    return [x for x in data if isinstance(x, dict)]


def check_dividend(data: Any) -> Tuple[bool, str]:
    rows = _list_dicts(data)
    if not rows:
        return False, "empty list"
    amounts = [float(r.get("amount") or r.get("motion_div") or r.get("div_amount") or r.get("cash_div") or 0) for r in rows]
    if not any(a > 0 for a in amounts):
        return False, f"all amount/cash_div zero (keys sample: {list(rows[0].keys())[:8]})"
    if "amount" not in rows[0]:
        return False, "missing amount alias field"
    return True, f"ok max_amount={max(amounts):.4f}"


def check_money_flow(data: Any) -> Tuple[bool, str]:
    rows = _list_dicts(data)
    if not rows:
        return False, "empty list"
    nets = [
        float(r.get("main_net") or r.get("net_mf_amount") or r.get("mainIn") or 0)
        for r in rows
    ]
    if not any(abs(n) > 1 for n in nets):
        return False, f"all main_net zero (keys: {list(rows[0].keys())[:8]})"
    return True, f"ok sample_main_net={nets[0]:.2f}"


def check_consensus_eps(data: Any) -> Tuple[bool, str]:
    rows = _list_dicts(data)
    if not rows:
        return False, "empty list"
    eps_vals = [float(r.get("eps") or r.get("mean") or 0) for r in rows]
    if not any(e > 0 for e in eps_vals):
        return False, "all eps/mean zero"
    if "eps" not in rows[0] and "mean" not in rows[0]:
        return False, "missing eps/mean"
    return True, f"ok eps={eps_vals[0]:.2f}"


def check_valuation(data: Any) -> Tuple[bool, str]:
    if not is_dataclass(data):
        return False, "not ValuationData"
    pe = getattr(data, "pe_ttm", None)
    dy = getattr(data, "dividend_yield", None)
    if pe is not None and float(pe) <= 0:
        return False, f"pe_ttm<=0 ({pe})"
    if dy is not None and float(dy) > 0.5:
        return False, f"dividend_yield not decimal? ({dy}) — expect <0.5 for 50%"
    return True, f"ok pe={pe} dy={dy}"


def check_report_forecast(data: Any) -> Tuple[bool, str]:
    rows = _list_dicts(data)
    if not rows:
        return False, "empty"
    if not any(float(r.get("eps") or 0) > 0 for r in rows):
        return False, "all eps zero"
    return True, "ok"


def check_valuation_calc(data: Any) -> Tuple[bool, str]:
    if not isinstance(data, dict):
        return False, "not dict"
    if data.get("pe_ttm") is None and data.get("eps_cur") is None:
        return False, "missing pe_ttm and eps_cur"
    return True, "ok"


# method_id -> semantic checker（仅对应有业务数据的接口）
SEMANTIC_CHECKS: Dict[str, CheckFn] = {
    "dividend": check_dividend,
    "money_flow": check_money_flow,
    "fund_flow_baidu": check_money_flow,
    "consensus_eps": check_consensus_eps,
    "valuation": check_valuation,
    "report_forecast": check_report_forecast,
    "valuation_calc": check_valuation_calc,
}
