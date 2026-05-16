"""返回结构契约测试（部分联网）。"""

import os
import sys

import pytest

_SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _SKILL_ROOT not in sys.path:
    sys.path.insert(0, _SKILL_ROOT)


def test_quote_is_dataclass_not_dict():
    from teakfds import TeakFDS
    from teakfds.models import QuoteData

    q = TeakFDS().quote("SH600519", use_cache=False)
    if q is None:
        pytest.skip("quote unavailable")
    assert isinstance(q, QuoteData)
    assert isinstance(q.current, (int, float))
    assert q.symbol.startswith("SH") or q.symbol.startswith("SZ")
    with pytest.raises(TypeError):
        _ = q["current"]


def test_kline_is_list_of_kline_data():
    from teakfds import TeakFDS
    from teakfds.models import KlineData

    bars = TeakFDS().kline("SH600519", period="day", count=3, use_cache=False)
    if not bars:
        pytest.skip("kline unavailable")
    assert isinstance(bars, list)
    assert isinstance(bars[0], KlineData)
    assert bars[0].date
    assert isinstance(bars[0].close, (int, float))
    with pytest.raises(TypeError):
        _ = bars[0]["close"]


def test_tushare_returns_list_dict():
    from teakfds import TeakFDS

    fds = TeakFDS()
    rows = fds.tushare(
        "daily",
        ts_code="600519.SH",
        start_date="20250501",
        end_date="20250508",
        fields="ts_code,trade_date,close",
    )
    if not rows:
        pytest.skip("tushare unavailable")
    assert isinstance(rows, list)
    assert isinstance(rows[0], dict)
    assert "trade_date" in rows[0]


@pytest.mark.integration
def test_report_forecast_dict_keys():
    from teakfds.providers.aggregate_provider import get_aggregate_provider

    rows = get_aggregate_provider().profit_forecast("SH600519")
    assert rows
    assert "year" in rows[0] and "eps" in rows[0]


@pytest.mark.integration
def test_announcement_list_dict_keys():
    from teakfds import TeakFDS

    rows = TeakFDS().announcement_list("SH600519")
    assert rows
    assert "title" in rows[0] and "source" in rows[0]


@pytest.mark.integration
def test_industry_comparison_structure():
    from teakfds import TeakFDS

    d = TeakFDS().industry_comparison(top_n=2)
    if not d:
        pytest.skip("industry_comparison unavailable")
    assert "top" in d and "total" in d
    assert isinstance(d["top"], list)
    assert "change_pct" in d["top"][0]
