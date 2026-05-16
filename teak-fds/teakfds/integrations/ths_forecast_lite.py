"""
同花顺盈利预测页轻量抓取（一致预期 EPS）。

同花顺 worth 页「预测年报每股收益」表（预测年报每股收益），
仅依赖 requests + pandas（可选）；无 pandas 时返回 None。
"""

from __future__ import annotations

from io import StringIO
from typing import Any, Dict, List, Optional

import requests

_TH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}


def _fds_to_code(symbol: str) -> str:
    s = (symbol or "").upper().strip()
    if s.startswith(("SH", "SZ", "BJ")):
        return s[2:]
    if "." in s:
        return s.split(".")[0]
    return s


def fetch_consensus_eps_ths(
    symbol: str,
    indicator: str = "预测年报每股收益",
) -> Optional[List[Dict[str, Any]]]:
    """
    机构一致预期 EPS（同花顺 worth 页）。

    Returns:
        [{year, count, min, mean, max, industry_avg}, ...]
    """
    if indicator != "预测年报每股收益":
        return None

    try:
        import pandas as pd
    except ImportError:
        return None

    code = _fds_to_code(symbol)
    url = f"https://basic.10jqka.com.cn/new/{code}/worth.html"
    try:
        resp = requests.get(url, headers=_TH_HEADERS, timeout=20)
        resp.encoding = "gbk"
    except Exception:
        return None

    if "本年度暂无机构做出业绩预测" in resp.text:
        return None

    try:
        tables = pd.read_html(StringIO(resp.text))
    except Exception:
        return None
    if not tables:
        return None

    df = tables[0]
    if df is None or df.empty:
        return None

    out: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        try:
            try:
                year_s = str(int(float(row.get("年度", ""))))
            except (TypeError, ValueError):
                year_s = str(row.get("年度", "")).strip()
            out.append(
                {
                    "year": year_s,
                    "eps": float(row.get("均值", 0) or 0),
                    "count": int(row.get("预测机构数", 0) or 0),
                    "min": float(row.get("最小值", 0) or 0),
                    "mean": float(row.get("均值", 0) or 0),
                    "max": float(row.get("最大值", 0) or 0),
                    "industry_avg": float(row.get("行业平均数", 0))
                    if "行业平均数" in df.columns
                    else None,
                }
            )
        except (TypeError, ValueError):
            continue
    return out or None
