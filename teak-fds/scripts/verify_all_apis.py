#!/usr/bin/env python3
"""
Teak-FDS 全量 API 契约验证（门面所有公开方法 + 语义检查）。

用法:
  python scripts/verify_all_apis.py              # 全量
  python scripts/verify_all_apis.py --strict     # 含数值/字段语义（推荐 CI）
  python scripts/verify_all_apis.py --symbol SZ300750
  python scripts/verify_all_apis.py --json
"""

from __future__ import annotations

import argparse
import inspect
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# 不自动执行联网调用的方法
SKIP_METHODS: Set[str] = {
    "refresh_undervalued_pool",
    "announcement_full_text",
    "clear_cache",
    "_resolve_symbol",
    "_init_providers",
    "_register_provider",
    "_to_ts_code",
    "_openclaw_root",
    "default_undervalued_pool_path",
    "_backup_undervalued_pool_json",
    "_screener_stock_to_candidate",
    "_normalize_lixinger_percentile_dict",
    "_kline_via_router",
    "_kline_daily_adj_composite",
    "_kline_from_tushare_pro_bar",
}

RECENT = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
TODAY = datetime.now().strftime("%Y%m%d")
MONTH = datetime.now().strftime("%Y%m")


def _build_call_table(symbol: str, ts_code: str, name: str) -> Dict[str, Callable[[Any], Any]]:
    """method_name -> lambda fds: result"""
    return {
        "quote": lambda f: f.quote(symbol),
        "batch_quote": lambda f: f.batch_quote([symbol, "SZ000001"]),
        "quote_ext": lambda f: f.quote_ext(symbol),
        "depth": lambda f: f.depth(symbol),
        "intraday": lambda f: f.intraday(symbol),
        "minute_kline": lambda f: f.minute_kline(symbol),
        "pankou": lambda f: f.pankou(symbol),
        "tick_data": lambda f: f.tick_data(symbol, count=20),
        "tick_data_history": lambda f: f.tick_data_history(symbol, "20250102", count=20),
        "kline": lambda f: f.kline(symbol, count=5),
        "pro_bar": lambda f: f.pro_bar(symbol, start_date=RECENT, end_date=TODAY),
        "stk_mins": lambda f: f.stk_mins(symbol, start_date=RECENT, end_date=TODAY, freq="5min"),
        "valuation": lambda f: f.valuation(symbol),
        "valuation_calc": lambda f: f.valuation_calc(symbol),
        "valuation_history": lambda f: f.valuation_history(symbol, years=3),
        "valuation_percentiles": lambda f: f.valuation_percentiles(symbol, years=5),
        "pe_percentile": lambda f: f.pe_percentile(symbol, years=5),
        "pb_percentile": lambda f: f.pb_percentile(symbol, years=5),
        "ps_percentile": lambda f: f.ps_percentile(symbol, years=5),
        "dyr_percentile": lambda f: f.dyr_percentile(symbol, years=5),
        "price_metric_percentile": lambda f: f.price_metric_percentile(symbol, "pe_ttm", 5),
        "dividend": lambda f: f.dividend(symbol),
        "consensus_eps": lambda f: f.consensus_eps(symbol),
        "income": lambda f: f.income(symbol),
        "balance_sheet": lambda f: f.balance_sheet(symbol),
        "cash_flow": lambda f: f.cash_flow(symbol),
        "financial_indicator": lambda f: f.financial_indicator(symbol),
        "income_df": lambda f: f.income_df(symbol),
        "balance_sheet_df": lambda f: f.balance_sheet_df(symbol),
        "cash_flow_df": lambda f: f.cash_flow_df(symbol),
        "finance_snapshot": lambda f: f.finance_snapshot(symbol),
        "f10": lambda f: f.f10(symbol),
        "xdxr": lambda f: f.xdxr(symbol),
        "forecast": lambda f: f.forecast(symbol, start_date=RECENT, end_date=TODAY),
        "express": lambda f: f.express(symbol, start_date=RECENT, end_date=TODAY),
        "report_list": lambda f: f.report_list(symbol, start_date=RECENT, end_date=TODAY),
        "report_forecast": lambda f: f.report_forecast(symbol),
        "report_rating": lambda f: f.report_rating(symbol),
        "institution_recommend": lambda f: f.institution_recommend(symbol),
        "institution_participation": lambda f: f.institution_participation(symbol),
        "eastmoney_reports": lambda f: f.eastmoney_reports(symbol, max_pages=1),
        "iwencai": lambda f: f.iwencai("市盈率小于30"),
        "announcement_list": lambda f: f.announcement_list(symbol),
        "latest_announcements": lambda f: f.latest_announcements(),
        "company_events": lambda f: f.company_events(),
        "search": lambda f: f.search(name, data_type="news"),
        "search_news": lambda f: f.search_news(name, days=7),
        "search_report": lambda f: f.search_report(name, count=5),
        "search_announcement": lambda f: f.search_announcement(name, days=30),
        "money_flow": lambda f: f.money_flow(symbol, days=5),
        "capital_flow": lambda f: f.capital_flow(symbol),
        "fund_flow_baidu": lambda f: f.fund_flow_baidu(symbol, days=5),
        "north_money_flow": lambda f: f.north_money_flow(start_date=RECENT, end_date=TODAY),
        "hsgt_top10": lambda f: f.hsgt_top10(),
        "north_money_realtime": lambda f: f.north_money_realtime(),
        "top_list": lambda f: f.top_list(),
        "limit_up_down": lambda f: f.limit_up_down(),
        "daily_dragon_tiger": lambda f: f.daily_dragon_tiger(),
        "hot_stocks": lambda f: f.hot_stocks(),
        "concept_blocks": lambda f: f.concept_blocks(symbol),
        "industry_comparison": lambda f: f.industry_comparison(top_n=5),
        "market_breadth": lambda f: f.market_breadth(),
        "index_quotes": lambda f: f.index_quotes(),
        "index_list": lambda f: f.index_list(market="SSE"),
        "index_kline": lambda f: f.index_kline("000001.SH", start_date=RECENT, end_date=TODAY),
        "cn_cpi": lambda f: f.cn_cpi(),
        "cn_ppi": lambda f: f.cn_ppi(),
        "cn_pmi": lambda f: f.cn_pmi(),
        "cn_gdp": lambda f: f.cn_gdp(),
        "cn_m": lambda f: f.cn_m(),
        "shibor": lambda f: f.shibor(),
        "insider_trading": lambda f: f.insider_trading(symbol),
        "top_holders": lambda f: f.top_holders(symbol),
        "top_float_holders": lambda f: f.top_float_holders(symbol),
        "shareholder_count": lambda f: f.shareholder_count(symbol),
        "managers": lambda f: f.managers(symbol),
        "main_business": lambda f: f.main_business(symbol, biz_type="P"),
        "share_unlock": lambda f: f.share_unlock(symbol),
        "survey_activities": lambda f: f.survey_activities(symbol),
        "watchlist_stocks": lambda f: f.watchlist_stocks(),
        "cube_rebalancing": lambda f: f.cube_rebalancing("ZH3404752", count=3),
        "cube_quote": lambda f: f.cube_quote(symbol),
        "cube_nav": lambda f: f.cube_nav("ZH3404752", days=30),
        "stock_basic": lambda f: f.stock_basic(symbol=symbol),
        "name_to_code": lambda f: f.name_to_code(name),
        "code_to_name": lambda f: f.code_to_name(symbol),
        "trade_cal": lambda f: f.trade_cal(start_date=RECENT, end_date=TODAY),
        "tushare": lambda f: f.tushare(
            "daily", ts_code=ts_code, start_date=RECENT, end_date=TODAY, fields="ts_code,trade_date,close"
        ),
        "get_provider": lambda f: f.get_provider("tencent"),
        "get_status": lambda f: f.get_status(),
        "health_check": lambda f: f.health_check(),
    }


# 允许 None（环境/权限）的接口
OPTIONAL_IDS: Set[str] = {
    "tick_data", "tick_data_history", "depth", "intraday", "minute_kline", "pankou",
    "stk_mins", "finance_snapshot", "f10", "valuation_history", "valuation_percentiles",
    "pe_percentile", "pb_percentile", "ps_percentile", "dyr_percentile", "price_metric_percentile",
    "income", "balance_sheet", "cash_flow", "financial_indicator",
    "report_list", "institution_recommend", "institution_participation", "iwencai",
    "latest_announcements", "company_events", "search", "search_news", "search_report",
    "search_announcement", "capital_flow", "north_money_flow", "hsgt_top10",
    "north_money_realtime", "top_list", "limit_up_down", "daily_dragon_tiger",
    "hot_stocks", "market_breadth", "index_quotes", "index_list", "index_kline",
    "cn_cpi", "cn_ppi", "cn_pmi", "cn_gdp", "cn_m", "shibor",
    "insider_trading", "top_holders", "top_float_holders", "shareholder_count",
    "managers", "main_business", "share_unlock", "survey_activities",
    "watchlist_stocks", "cube_rebalancing", "cube_quote", "cube_nav",
    "stock_basic", "trade_cal", "get_provider", "pro_bar", "xdxr", "forecast", "express",
    "fund_flow_baidu",
}


def _discover_public_methods(fds: Any) -> List[str]:
    names = []
    for name, member in inspect.getmembers(fds.__class__):
        if name.startswith("_") or name in SKIP_METHODS:
            continue
        if callable(member) and not isinstance(inspect.getattr_static(fds.__class__, name, None), property):
            names.append(name)
    return sorted(names)


def run_all(symbol: str, strict: bool) -> Dict[str, Any]:
    from teakfds import TeakFDS
    from teakfds.api_semantics import SEMANTIC_CHECKS

    ts_code = symbol[2:] + "." + symbol[:2] if symbol[:2] in ("SH", "SZ", "BJ") else symbol
    name_map = {"SH600519": "贵州茅台", "SZ300750": "宁德时代", "SZ000001": "平安银行"}
    name = name_map.get(symbol, "贵州茅台")

    fds = TeakFDS(use_cache=False)
    calls = _build_call_table(symbol, ts_code, name)
    all_methods = _discover_public_methods(fds)

    results: List[Dict[str, Any]] = []
    passed = failed = skipped = warned = 0

    for mid in all_methods:
        entry: Dict[str, Any] = {"id": mid, "callable": mid in calls}
        if mid not in calls:
            entry["status"] = "skip"
            entry["detail"] = "no test harness (internal/helper)"
            skipped += 1
            results.append(entry)
            continue

        try:
            data = calls[mid](fds)
            entry["return_type"] = type(data).__name__
            if data is None:
                if mid in OPTIONAL_IDS:
                    entry["status"] = "skip"
                    entry["detail"] = "returned None"
                    skipped += 1
                else:
                    entry["status"] = "fail"
                    entry["detail"] = "returned None"
                    failed += 1
                results.append(entry)
                continue

            if strict and mid in SEMANTIC_CHECKS:
                ok, msg = SEMANTIC_CHECKS[mid](data)
                entry["semantic"] = msg
                if not ok:
                    entry["status"] = "fail"
                    entry["detail"] = f"semantic: {msg}"
                    failed += 1
                    results.append(entry)
                    continue

            entry["status"] = "pass"
            entry["detail"] = entry.get("semantic", "ok")
            if isinstance(data, list) and data and isinstance(data[0], dict):
                entry["sample_keys"] = list(data[0].keys())[:12]
            passed += 1
        except TypeError as e:
            if "unexpected keyword" in str(e):
                entry["status"] = "fail"
                entry["detail"] = f"kwargs: {e}"
                failed += 1
            elif mid in OPTIONAL_IDS:
                entry["status"] = "skip"
                entry["detail"] = str(e)
                skipped += 1
            else:
                entry["status"] = "fail"
                entry["detail"] = str(e)
                failed += 1
        except Exception as e:
            if mid in OPTIONAL_IDS:
                entry["status"] = "skip"
                entry["detail"] = f"{type(e).__name__}: {e}"
                skipped += 1
            else:
                entry["status"] = "fail"
                entry["detail"] = f"{type(e).__name__}: {e}"
                failed += 1
        results.append(entry)

    return {
        "timestamp": datetime.now().isoformat(),
        "symbol": symbol,
        "strict": strict,
        "discovered": len(all_methods),
        "tested": len(calls),
        "summary": {"pass": passed, "fail": failed, "skip": skipped, "warn": warned, "total": len(results)},
        "results": results,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Teak-FDS full API verification")
    ap.add_argument("--strict", action="store_true", help="语义/字段契约检查")
    ap.add_argument("--symbol", default="SH600519,SZ300750", help="逗号分隔标的")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    symbols = [s.strip() for s in args.symbol.split(",") if s.strip()]
    reports = [run_all(sym, args.strict) for sym in symbols]

    if args.json:
        print(json.dumps(reports if len(reports) > 1 else reports[0], ensure_ascii=False, indent=2))
    else:
        total_fail = 0
        for rep in reports:
            s = rep["summary"]
            total_fail += s["fail"]
            print(f"\n=== {rep['symbol']} (discovered={rep['discovered']} tested={rep['tested']}) ===")
            print(f"PASS {s['pass']}  FAIL {s['fail']}  SKIP {s['skip']}  TOTAL {s['total']}")
            for r in rep["results"]:
                if r["status"] == "fail":
                    print(f"  ✗ [{r['id']}] {r.get('detail', '')}")
            fails = [r for r in rep["results"] if r["status"] == "fail"]
            if not fails:
                print("  (no failures)")
        print(f"\nOverall: {'FAIL' if total_fail else 'PASS'}")

    sys.exit(1 if any(r["summary"]["fail"] for r in reports) else 0)


if __name__ == "__main__":
    main()
