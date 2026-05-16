"""normalize_finance 单元测试。"""

from teakfds.normalize_finance import (
    dividend_yield_decimal,
    filter_dividend_rows,
    normalize_consensus_eps_rows,
    normalize_dividend_rows,
    normalize_money_flow_rows,
)


def test_dividend_yield_decimal():
    assert dividend_yield_decimal(1.8545) == 0.018545
    assert dividend_yield_decimal(0.0185) == 0.0185


def test_normalize_dividend_amount_alias():
    rows = [{"end_date": "20251231", "div_proc": "实施", "cash_div": 6.957}]
    out = normalize_dividend_rows(rows)
    assert out[0]["amount"] == 6.957
    assert out[0]["div_amount"] == 6.957


def test_filter_dividend_rows():
    rows = [
        {"end_date": "20251231", "div_proc": "预案", "cash_div": 0.0},
        {"end_date": "20251231", "div_proc": "实施", "cash_div": 6.957},
    ]
    out = filter_dividend_rows(rows)
    assert len(out) == 1
    assert out[0]["cash_div"] == 6.957


def test_normalize_money_flow_tushare():
    raw = [{"trade_date": "20260515", "net_mf_amount": 10407.45}]
    out = normalize_money_flow_rows(raw, source="tushare")
    assert out[0]["main_net"] == 10407.45


def test_normalize_consensus_eps_eps_alias():
    rows = [{"year": "2026.0", "mean": 20.77, "count": 31}]
    out = normalize_consensus_eps_rows(rows)
    assert out[0]["year"] == "2026"
    assert out[0]["eps"] == 20.77
