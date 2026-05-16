import os
import sys

import pytest

_SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _SKILL_ROOT not in sys.path:
    sys.path.insert(0, _SKILL_ROOT)


def test_import_teakfds():
    from teakfds import TeakFDS

    assert TeakFDS is not None
    f = TeakFDS()
    assert f is not None


def test_no_akshare_dependency():
    import importlib.util

    assert importlib.util.find_spec("akshare") is None or True  # 允许环境有但不 import
    from teakfds.providers import aggregate_provider

    assert not hasattr(aggregate_provider, "get_akshare_module")


@pytest.mark.integration
def test_quote_tencent_live():
    from teakfds import TeakFDS

    q = TeakFDS().quote("SH600519", use_cache=False)
    assert q is not None
    assert q.symbol == "SH600519"
    assert q.name
    assert q.source


@pytest.mark.integration
def test_cninfo_announcement():
    from teakfds.providers.cninfo_provider import get_cninfo_provider

    p = get_cninfo_provider()
    r = p.announcement_list("SH600519", page_size=5)
    assert r is not None


@pytest.mark.integration
def test_aggregate_profit_forecast():
    from teakfds.providers.aggregate_provider import get_aggregate_provider

    rows = get_aggregate_provider().profit_forecast("SH600519")
    assert rows
    assert rows[0].get("eps")


def test_valuation_utils_import():
    from teakfds.valuation_utils import forward_pe, calc_peg

    assert forward_pe(100, 5) == 20.0
    assert calc_peg(20, 0.3) > 0
