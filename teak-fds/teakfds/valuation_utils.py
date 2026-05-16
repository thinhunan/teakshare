#!/usr/bin/env python3
"""
估值计算工具

提供:
- forward_pe: 前向 PE（当前价 / 一致预期 EPS）
- pe_digestion: PE 消化时间（当前 PE 回归目标 PE 所需年数）
- calc_peg: PEG = 前向PE / (CAGR × 100)
- full_valuation: 单票完整估值分析
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional


def forward_pe(price: float, eps_forecast: float) -> float:
    """前向 PE = 当前股价 / 未来年度一致预期 EPS"""
    if eps_forecast <= 0:
        return float("inf")
    return price / eps_forecast


def pe_digestion(current_pe: float, cagr: float, target_pe: float = 30) -> float:
    """当前 PE 消化到目标 PE 需要多少年。"""
    if current_pe <= target_pe:
        return 0.0
    if cagr <= 0:
        return float("inf")
    return math.log(current_pe / target_pe) / math.log(1 + cagr)


def calc_peg(pe: float, cagr: float) -> float:
    """PEG = 前向PE / (CAGR × 100)"""
    if cagr <= 0:
        return float("inf")
    return pe / (cagr * 100)


def full_valuation(fds, symbol: str) -> Optional[Dict[str, Any]]:
    """单票完整估值分析（依赖 TeakFDS / FinanceDataSource 实例）。"""
    quote = fds.quote_ext(symbol)
    if not quote or not quote.current:
        return None

    price = quote.current
    pe_ttm = getattr(quote, "pe_ttm", None) or 0
    pb = getattr(quote, "pb", None) or 0
    mcap = getattr(quote, "total_market_cap", None) or 0
    mcap_yi = mcap / 1e8 if mcap > 1e6 else mcap
    name = getattr(quote, "name", symbol)

    eps_cur = None
    eps_next = None
    analyst_count = 0

    try:
        forecast = fds.report_forecast(symbol)
        if forecast:
            sorted_years = sorted(set(f.get("year", "") for f in forecast if f.get("year")))
            for f in forecast:
                y = str(f.get("year", ""))
                if sorted_years and y == str(sorted_years[0]):
                    eps_cur = f.get("eps")
                    analyst_count = f.get("count", 0)
                elif len(sorted_years) > 1 and y == str(sorted_years[1]):
                    eps_next = f.get("eps")
    except Exception:
        pass

    if eps_cur is None:
        try:
            rows = fds.consensus_eps(symbol)
            if rows:
                sorted_rows = sorted(rows, key=lambda r: str(r.get("year", "")))
                if sorted_rows:
                    eps_cur = sorted_rows[0].get("mean")
                    analyst_count = sorted_rows[0].get("count", 0)
                if len(sorted_rows) > 1:
                    eps_next = sorted_rows[1].get("mean")
        except Exception:
            pass

    pe_fwd = forward_pe(price, eps_cur) if eps_cur else None
    cagr = (eps_next / eps_cur - 1) if (eps_cur and eps_next and eps_cur > 0) else None
    peg = calc_peg(pe_fwd, cagr) if (pe_fwd and cagr and pe_fwd != float("inf")) else None
    digest = pe_digestion(pe_fwd, cagr) if (pe_fwd and cagr and pe_fwd != float("inf")) else None

    return {
        "name": name,
        "price": price,
        "mcap_yi": round(mcap_yi, 2) if mcap_yi else None,
        "pe_ttm": round(pe_ttm, 2) if pe_ttm else None,
        "pb": round(pb, 2) if pb else None,
        "eps_cur": round(eps_cur, 4) if eps_cur else None,
        "eps_next": round(eps_next, 4) if eps_next else None,
        "pe_fwd": round(pe_fwd, 1) if pe_fwd and pe_fwd != float("inf") else None,
        "cagr_pct": round(cagr * 100, 1) if cagr else None,
        "peg": round(peg, 2) if peg and peg != float("inf") else None,
        "digest_years": round(digest, 1) if digest and digest != float("inf") else None,
        "analyst_count": analyst_count,
    }
