"""Tushare 财务三表 → teakfds.models 统一模型。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from teakfds.models import BalanceData, CashFlowData, IncomeData


def _f(row: Dict[str, Any], *keys: str) -> Optional[float]:
    for k in keys:
        v = row.get(k)
        if v is None or v == "":
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


def _period(row: Dict[str, Any]) -> str:
    return str(row.get("end_date") or row.get("period") or "")


class FinancialAdapter:
    @staticmethod
    def from_tushare_income(rows: List[Dict[str, Any]], symbol: str = "") -> List[IncomeData]:
        out: List[IncomeData] = []
        for row in rows or []:
            out.append(
                IncomeData(
                    period=_period(row),
                    revenue=_f(row, "total_revenue", "revenue"),
                    operate_profit=_f(row, "operate_profit"),
                    total_profit=_f(row, "total_profit"),
                    net_profit=_f(row, "n_income", "net_profit"),
                    net_profit_attr=_f(row, "n_income_attr_p", "net_profit_attr"),
                    eps=_f(row, "basic_eps", "eps"),
                    source="tushare",
                )
            )
        return out

    @staticmethod
    def from_tushare_balance(rows: List[Dict[str, Any]], symbol: str = "") -> List[BalanceData]:
        out: List[BalanceData] = []
        for row in rows or []:
            out.append(
                BalanceData(
                    period=_period(row),
                    total_assets=_f(row, "total_assets"),
                    total_liab=_f(row, "total_liab"),
                    total_equity=_f(row, "total_hldr_eqy_exc_min_int", "total_equity"),
                    total_equity_attr=_f(row, "total_hldr_eqy_inc_min_int", "total_equity_attr"),
                    current_assets=_f(row, "total_cur_assets", "current_assets"),
                    current_liab=_f(row, "total_cur_liab", "current_liab"),
                    source="tushare",
                )
            )
        return out

    @staticmethod
    def from_tushare_cashflow(rows: List[Dict[str, Any]], symbol: str = "") -> List[CashFlowData]:
        out: List[CashFlowData] = []
        for row in rows or []:
            nca = _f(row, "n_cashflow_act")
            ninv = _f(row, "n_cashflow_inv_act")
            nfnc = _f(row, "n_cash_flows_fnc_act", "n_cash_flows_fun_act")
            free = _f(row, "free_cashflow")
            if free is None and nca is not None and ninv is not None:
                free = nca + ninv
            out.append(
                CashFlowData(
                    period=_period(row),
                    n_cashflow_act=nca,
                    n_cashflow_inv_act=ninv,
                    n_cash_flows_fnc_act=nfnc,
                    free_cashflow=free,
                    source="tushare",
                )
            )
        return out
