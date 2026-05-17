"""
teakfds — Agent 用统一金融数据源（Teak-FDS skill 核心包）。

使用方式::

    from teakfds import TeakFDS
    fds = TeakFDS()
    q = fds.quote("SH600519")

CLI（需 pip install -e .）::

    teakfds quote SH600519 --json
    python -m teakfds quote SH600519 --json
"""

from __future__ import annotations

from teakfds.bootstrap import ensure_skill_path

ensure_skill_path()

from teakfds.finance_data_source import (
    FinanceDataSource,
    TeakFDS,
    DataProxy,
    get_finance_data_source,
    get_dataproxy,
    quote,
    kline,
    valuation,
    valuation_percentiles,
    name_to_code,
    code_to_name,
    search,
)

__all__ = [
    "FinanceDataSource",
    "TeakFDS",
    "DataProxy",
    "get_finance_data_source",
    "get_dataproxy",
    "quote",
    "kline",
    "valuation",
    "valuation_percentiles",
    "name_to_code",
    "code_to_name",
    "search",
]

__version__ = "1.0.5"
