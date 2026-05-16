#!/usr/bin/env python3
"""Tushare 表格数据：统一为 list[dict]，不依赖 pandas。"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

Row = Dict[str, Any]


def is_null(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    return False


def not_null(v: Any) -> bool:
    return not is_null(v)


def records_empty(rows: Optional[Sequence[Any]]) -> bool:
    return rows is None or len(rows) == 0


def head_records(rows: Optional[List[Row]], n: int) -> Optional[List[Row]]:
    if rows is None:
        return None
    return rows[:n]


def coerce_tushare_table(data: Any) -> Optional[List[Row]]:
    """将 Tushare 返回结果规范为 list[dict]；兼容遗留 pandas.DataFrame（若存在）。"""
    if data is None:
        return None
    if isinstance(data, list):
        return data if data else None
    if hasattr(data, "empty") and data.empty:
        return None
    if hasattr(data, "iterrows"):
        out: List[Row] = []
        for _, row in data.iterrows():
            if hasattr(row, "to_dict"):
                out.append(dict(row.to_dict()))
            else:
                out.append(dict(row))
        return out if out else None
    return None


def iter_tushare_rows(data: Any) -> Iterable[Row]:
    rows = coerce_tushare_table(data)
    if not rows:
        return
    yield from rows


def safe_float(row: Row, key: str, default: float = 0.0) -> float:
    v = row.get(key)
    if is_null(v):
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def safe_int(row: Row, key: str, default: int = 0) -> int:
    v = row.get(key)
    if is_null(v):
        return default
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def safe_optional_float(row: Row, key: str) -> Optional[float]:
    v = row.get(key)
    if is_null(v):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
