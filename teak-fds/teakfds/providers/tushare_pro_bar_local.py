#!/usr/bin/env python3
"""
本地实现 tushare.pro_bar（股票 asset=E，freq=D/W/M），不依赖 tushare / pandas。

逻辑对齐 waditu/tushare tushare/pro/data_pro.py 中 asset=='E' 分支。
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

PRICE_COLS = ["open", "close", "high", "low", "pre_close"]
FORMAT = lambda x: float("%.2f" % float(x))  # noqa: E731


def _fmt_price(x: float) -> float:
    return FORMAT(x)


def _to_float(v: Any, default: float = 0.0) -> float:
    if v is None or v == "":
        return default
    if isinstance(v, float) and math.isnan(v):
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _sort_by_trade_date(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(rows, key=lambda r: str(r.get("trade_date", "")))


def _merge_on_trade_date(
    base: List[Dict[str, Any]],
    extra: List[Dict[str, Any]],
    keys: List[str],
) -> List[Dict[str, Any]]:
    xm: Dict[str, Dict[str, Any]] = {}
    for r in extra:
        d = str(r.get("trade_date", ""))
        if not d:
            continue
        xm[d] = r
    out: List[Dict[str, Any]] = []
    for r in base:
        nr = dict(r)
        d = str(nr.get("trade_date", ""))
        if d in xm:
            for k in keys:
                if k in xm[d]:
                    nr[k] = xm[d][k]
        out.append(nr)
    return out


def _bfill_adj(vals: List[Optional[float]]) -> List[Optional[float]]:
    """与 pandas bfill 一致：用后面的有效值向前填。"""
    n = len(vals)
    out: List[Optional[float]] = [None] * n
    last: Optional[float] = None
    for i in range(n - 1, -1, -1):
        v = vals[i]
        if v is not None and not (isinstance(v, float) and math.isnan(v)):
            last = float(v)
        out[i] = last
    return out


def _rolling_mean(vals: List[float], window: int) -> List[float]:
    out: List[float] = []
    for i in range(len(vals)):
        start = max(0, i - window + 1)
        chunk = vals[start : i + 1]
        out.append(sum(chunk) / len(chunk))
    return out


def pro_bar(
    ts_code: str = "",
    pro_api: Any = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    freq: str = "D",
    asset: str = "E",
    exchange: str = "",
    adj: Optional[str] = None,
    ma: Optional[List[int]] = None,
    factors: Optional[List[str]] = None,
    contract_type: str = "",
    retry_count: int = 3,
) -> Any:
    """
    与 tushare.pro_bar 对齐的子集：asset=E 股票，freq 为 D/W/M。

    返回 list[dict]（列名与 Tushare 日线等接口一致），不返回 DataFrame。

    pro_api 需具备 .daily / .weekly / .monthly / .adj_factor / .daily_basic 方法。
    """
    if pro_api is None:
        raise ValueError("pro_bar: pro_api is required")

    if ma is None:
        ma = []

    ts_code = ts_code.strip().upper()
    asset = asset.strip().upper()
    freq = freq.strip().upper()

    if asset != "E":
        raise NotImplementedError(
            f"pro_bar_local 当前仅支持 asset=E（股票），收到 asset={asset}"
        )

    last_err: Optional[Exception] = None
    for _ in range(retry_count):
        try:
            api = pro_api
            rows: Optional[List[Dict[str, Any]]] = None

            if freq == "D":
                raw = api.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
                rows = _ensure_rows(raw)
                if factors and rows:
                    try:
                        db_raw = api.daily_basic(
                            ts_code=ts_code, start_date=start_date, end_date=end_date
                        )
                        db = _ensure_rows(db_raw)
                        if db:
                            sample = db[0]
                            extra_keys = [
                                c
                                for c in ("turnover_rate", "volume_ratio")
                                if c in sample
                            ]
                            if extra_keys:
                                rows = _merge_on_trade_date(rows, db, extra_keys)
                                if ("tor" in factors) and ("vr" not in factors):
                                    for r in rows:
                                        r.pop("volume_ratio", None)
                                if ("vr" in factors) and ("tor" not in factors):
                                    for r in rows:
                                        r.pop("turnover_rate", None)
                    except Exception:
                        pass
            elif freq == "W":
                raw = api.weekly(
                    ts_code=ts_code, start_date=start_date, end_date=end_date
                )
                rows = _ensure_rows(raw)
            elif freq == "M":
                raw = api.monthly(
                    ts_code=ts_code, start_date=start_date, end_date=end_date
                )
                rows = _ensure_rows(raw)
            else:
                raise ValueError(f"不支持的 freq={freq}（支持 D/W/M）")

            if not rows:
                return None

            rows = _sort_by_trade_date(rows)

            if adj is not None:
                f_raw = api.adj_factor(
                    ts_code=ts_code, start_date=start_date, end_date=end_date
                )
                fcts = _ensure_rows(f_raw)
                if not fcts:
                    return None
                fcts_s = _sort_by_trade_date(
                    [{k: r[k] for k in r if k in ("trade_date", "adj_factor")} for r in fcts]
                )
                first_af = _to_float(fcts_s[0].get("adj_factor"))
                if adj != "hfq" and first_af == 0.0:
                    return None

                rows = _merge_on_trade_date(rows, fcts_s, ["adj_factor"])
                af_list = [_to_float(r.get("adj_factor"), float("nan")) for r in rows]
                # 用 None 表示缺失以便 bfill
                af_none: List[Optional[float]] = [
                    None
                    if (isinstance(x, float) and math.isnan(x))
                    else float(x)
                    for x in af_list
                ]
                af_filled = _bfill_adj(af_none)
                for i, r in enumerate(rows):
                    r["adj_factor"] = af_filled[i]

                for col in PRICE_COLS:
                    if not any(col in r for r in rows):
                        continue
                    for r in rows:
                        v = _to_float(r.get(col))
                        af = r.get("adj_factor")
                        if af is None:
                            continue
                        afv = float(af)
                        if adj == "hfq":
                            r[col] = _fmt_price(v * afv)
                        else:
                            r[col] = _fmt_price(v * afv / first_af) if first_af else v
                        r[col] = float(r[col])
                for r in rows:
                    r.pop("adj_factor", None)

            closes = [_to_float(r.get("close")) for r in rows]
            pres = [_to_float(r.get("pre_close")) for r in rows]
            for i, r in enumerate(rows):
                r["change"] = closes[i] - pres[i]
                if i == 0:
                    r["pct_change"] = None
                else:
                    prev_c = closes[i - 1]
                    r["pct_change"] = (
                        (closes[i] - prev_c) / prev_c * 100 if prev_c != 0 else None
                    )

            if ma:
                vols = [_to_float(r.get("vol")) for r in rows]
                for a in ma:
                    if isinstance(a, int) and a > 0:
                        m_c = _rolling_mean(closes, a)
                        m_v = _rolling_mean(vols, a)
                        for i, r in enumerate(rows):
                            r[f"ma{a}"] = float(_fmt_price(m_c[i]))
                            r[f"ma_v{a}"] = float(_fmt_price(m_v[i]))

            return rows
        except Exception as e:
            last_err = e
            continue

    if last_err:
        raise last_err
    return None


def _ensure_rows(raw: Any) -> Optional[List[Dict[str, Any]]]:
    if raw is None:
        return None
    if isinstance(raw, list):
        return raw if raw else None
    if hasattr(raw, "empty") and raw.empty:
        return None
    if hasattr(raw, "to_dict"):
        rec = raw.to_dict(orient="records")
        return rec if rec else None
    return None
