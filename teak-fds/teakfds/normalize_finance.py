"""金融数据字段归一化（资金流向、股息率、分红、一致预期等）。"""

from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, List, Optional

from teakfds.tushare_table import Row, safe_float, safe_optional_float


def call_with_supported_kwargs(fn: Callable[..., Any], **kwargs: Any) -> Any:
    """仅传入被调用方签名支持的参数，避免 provider 间 kwargs 不兼容。"""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return fn(**kwargs)
    filtered = {k: v for k, v in kwargs.items() if k in params}
    return fn(**filtered)


def dividend_yield_decimal(value: Optional[float]) -> Optional[float]:
    """
    统一股息率为小数：0.0185 表示 1.85%。
    理杏仁/Tushare 常返回百分数（如 1.85）；已为小数则保持不变。
    """
    if value is None:
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if abs(x) < 1e-12:
        return 0.0
    if abs(x) > 0.2:
        return x / 100.0
    return x


def _year_str(raw: Any) -> str:
    if raw is None:
        return ""
    try:
        y = int(float(raw))
        return str(y)
    except (TypeError, ValueError):
        return str(raw).strip()


def normalize_consensus_eps_rows(rows: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
    """一致预期：规范 year、补充 eps/growth 别名。"""
    if not rows:
        return None
    out: List[Dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        mean = r.get("mean")
        if mean is None:
            mean = r.get("eps")
        try:
            mean_f = float(mean) if mean is not None else None
        except (TypeError, ValueError):
            mean_f = None
        year = _year_str(r.get("year"))
        if not year:
            continue
        item = dict(r)
        item["year"] = year
        if mean_f is not None:
            item["mean"] = mean_f
            item["eps"] = mean_f
        min_v = item.get("min")
        max_v = item.get("max")
        if min_v is not None and max_v is not None:
            try:
                mn, mx = float(min_v), float(max_v)
                if mn > 0:
                    item["growth"] = (mx - mn) / mn
            except (TypeError, ValueError):
                pass
        out.append(item)
    return out or None


def consensus_eps_has_signal(rows: Optional[List[Dict[str, Any]]]) -> bool:
    if not rows:
        return False
    for r in rows:
        v = r.get("mean", r.get("eps"))
        try:
            if v is not None and float(v) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def filter_dividend_rows(rows: Optional[List[Row]]) -> Optional[List[Row]]:
    """过滤无实际分红记录（cash_div/stk_div 均为 0）。"""
    if not rows:
        return None
    kept: List[Row] = []
    for r in rows:
        cash = safe_float(r, "cash_div", 0.0)
        stk = safe_float(r, "stk_div", 0.0)
        if cash > 0 or stk > 0:
            kept.append(dict(r))
    if not kept:
        return None
    # 同报告期优先保留「实施」
    by_period: Dict[str, Row] = {}
    for r in kept:
        key = str(r.get("end_date") or r.get("ann_date") or "")
        proc = str(r.get("div_proc") or "")
        prev = by_period.get(key)
        if prev is None:
            by_period[key] = r
            continue
        prev_proc = str(prev.get("div_proc") or "")
        if proc == "实施" and prev_proc != "实施":
            by_period[key] = r
        elif proc == "实施" and prev_proc == "实施":
            if safe_float(r, "cash_div", 0) > safe_float(prev, "cash_div", 0):
                by_period[key] = r
    ordered = sorted(by_period.values(), key=lambda x: str(x.get("end_date") or ""), reverse=True)
    return ordered


def normalize_money_flow_rows(
    rows: Any, source: str = "", days: Optional[int] = None
) -> Optional[List[Dict[str, Any]]]:
    """统一资金流向为 Agent 友好字段（含 main_net / change_pct）。"""
    if rows is None:
        return None
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list) or not rows:
        return None

    out: List[Dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        item: Dict[str, Any] = {"source": source or r.get("source", "")}

        if "net_mf_amount" in r or "trade_date" in r:
            td = str(r.get("trade_date") or r.get("date") or "")
            net = safe_optional_float(r, "net_mf_amount")
            item.update(
                {
                    "trade_date": td,
                    "date": td,
                    "main_net": net if net is not None else 0.0,
                    "net_mf_amount": net if net is not None else 0.0,
                    "main_inflow": safe_float(r, "buy_lg_amount") + safe_float(r, "buy_elg_amount"),
                    "main_outflow": safe_float(r, "sell_lg_amount") + safe_float(r, "sell_elg_amount"),
                    "buy_elg_amount": safe_optional_float(r, "buy_elg_amount"),
                    "buy_lg_amount": safe_optional_float(r, "buy_lg_amount"),
                    "sell_elg_amount": safe_optional_float(r, "sell_elg_amount"),
                    "sell_lg_amount": safe_optional_float(r, "sell_lg_amount"),
                }
            )
        elif "mainIn" in r or "main_net" in r:
            dt = str(r.get("date") or r.get("time") or "")
            main = r.get("mainIn", r.get("main_net"))
            try:
                main_f = float(main) if main not in (None, "") else 0.0
            except (TypeError, ValueError):
                main_f = 0.0
            chg = r.get("change_pct", r.get("ratio"))
            try:
                chg_f = float(chg) if chg not in (None, "") else None
            except (TypeError, ValueError):
                chg_f = None
            item.update(
                {
                    "trade_date": dt.replace("-", "")[:8] if dt else dt,
                    "date": dt,
                    "main_net": main_f,
                    "net_mf_amount": main_f,
                    "change_pct": chg_f,
                    "superNetIn": r.get("superNetIn"),
                    "largeNetIn": r.get("largeNetIn"),
                    "close": r.get("close"),
                }
            )
        elif "main_net" in r or "main_inflow" in r:
            item.update(dict(r))
            if "main_net" not in item and "main_inflow" in item:
                mi = safe_float(r, "main_inflow")
                mo = safe_float(r, "main_outflow")
                item["main_net"] = mi - mo
                item["net_mf_amount"] = item["main_net"]
        else:
            item.update(dict(r))

        out.append(item)

    if days and len(out) > days:
        out = out[:days]
    return out or None
