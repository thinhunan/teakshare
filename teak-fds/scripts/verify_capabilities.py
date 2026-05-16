#!/usr/bin/env python3
"""
Teak-FDS 能力矩阵验证（对照 finance-data-source + 原 AkShare 门面能力）。

用法:
  python scripts/verify_capabilities.py           # 联网全量
  python scripts/verify_capabilities.py --quick   # 核心项
  python scripts/verify_capabilities.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from dataclasses import is_dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

SYMBOL = "SH600519"
TS_CODE = "600519.SH"
RECENT = (datetime.now() - timedelta(days=14)).strftime("%Y%m%d")
TODAY = datetime.now().strftime("%Y%m%d")


def _ok(data: Any, checker: Callable[[Any], bool]) -> Tuple[bool, str]:
    if data is None:
        return False, "returned None"
    try:
        if checker(data):
            return True, "ok"
        return False, "shape mismatch"
    except Exception as e:
        return False, str(e)


def build_cases(quick: bool) -> List[Dict[str, Any]]:
    from teakfds import TeakFDS
    from teakfds.models import DepthData, FinancialIndicator, IntradayData, KlineData, QuoteData, ValuationData

    fds = TeakFDS(use_cache=False)

    def case(cid, name, fn, check, origin, optional=False):
        return {"id": cid, "name": name, "call": fn, "check": check, "origin": origin, "optional": optional}

    cases = [
        case("quote", "实时行情", lambda: fds.quote(SYMBOL), lambda d: is_dataclass(d) and isinstance(d, QuoteData) and d.current, "FDS"),
        case("batch_quote", "批量行情", lambda: fds.batch_quote([SYMBOL]), lambda d: isinstance(d, list) and d and is_dataclass(d[0]), "FDS"),
        case("quote_ext", "扩展行情", lambda: fds.quote_ext(SYMBOL), lambda d: is_dataclass(d) and isinstance(d, QuoteData), "FDS"),
        case("depth", "五档盘口", lambda: fds.depth(SYMBOL), lambda d: d is None or (is_dataclass(d) and isinstance(d, DepthData)), "FDS", optional=True),
        case("kline", "日K线", lambda: fds.kline(SYMBOL, count=5), lambda d: isinstance(d, list) and d and isinstance(d[0], KlineData), "FDS"),
        case("pro_bar", "复权K线", lambda: fds.pro_bar(SYMBOL, start_date=RECENT, end_date=TODAY), lambda d: d is None or (isinstance(d, list) and (not d or isinstance(d[0], dict))), "FDS", optional=True),
        case("valuation", "估值", lambda: fds.valuation(SYMBOL), lambda d: is_dataclass(d) and isinstance(d, ValuationData), "FDS"),
        case("valuation_calc", "前向PE/PEG", lambda: fds.valuation_calc(SYMBOL), lambda d: d is None or (isinstance(d, dict) and "pe_ttm" in d), "FDS"),
        case("consensus_eps", "一致预期EPS", lambda: fds.consensus_eps(SYMBOL), lambda d: d is None or (isinstance(d, list) and (not d or isinstance(d[0], dict))), "FDS/Ak"),
        case("pe_percentile", "PE分位", lambda: fds.pe_percentile(SYMBOL, years=5), lambda d: d is None or isinstance(d, dict), "FDS", optional=True),
        case("tushare_daily", "Tushare逃生舱", lambda: fds.tushare("daily", ts_code=TS_CODE, start_date=RECENT, end_date=TODAY, fields="ts_code,trade_date,close"), lambda d: isinstance(d, list) and d and isinstance(d[0], dict), "FDS"),
        case("financial_indicator", "财务指标", lambda: fds.financial_indicator(SYMBOL), lambda d: d is None or isinstance(d, FinancialIndicator), "FDS", optional=True),
        case("income_df", "利润表", lambda: fds.income_df(SYMBOL), lambda d: d is None or (isinstance(d, list) and (not d or isinstance(d[0], dict))), "FDS", optional=True),
        case("announcement_list", "公告列表", lambda: fds.announcement_list(SYMBOL), lambda d: isinstance(d, list) and d and "title" in d[0], "FDS/Ak"),
        case("report_forecast", "盈利预测", lambda: fds.report_forecast(SYMBOL), lambda d: isinstance(d, list) and d and "year" in d[0], "Ak"),
        case("report_rating", "机构评级", lambda: fds.report_rating(SYMBOL), lambda d: d is None or (isinstance(d, list) and (not d or isinstance(d[0], dict))), "Ak", optional=True),
        case("industry_comparison", "行业对比", lambda: fds.industry_comparison(top_n=3), lambda d: d and "top" in d, "Ak", optional=True),
        case("search", "搜索", lambda: fds.search("贵州茅台", data_type="news"), lambda d: d is None or (isinstance(d, list) and (not d or "title" in d[0])), "FDS"),
        case("money_flow", "个股资金流", lambda: fds.money_flow(SYMBOL, days=5), lambda d: d is None or isinstance(d, list), "FDS", optional=True),
        case("hsgt_top10", "港通十大", lambda: fds.hsgt_top10(), lambda d: d is None or (isinstance(d, list) and (not d or isinstance(d[0], dict))), "FDS", optional=True),
        case("hot_stocks", "强势股", lambda: fds.hot_stocks(), lambda d: d is None or isinstance(d, list), "FDS", optional=True),
        case("concept_blocks", "概念板块", lambda: fds.concept_blocks(SYMBOL), lambda d: isinstance(d, dict) and ("industry" in d or "concept" in d), "FDS", optional=True),
        case("daily_dragon_tiger", "龙虎榜", lambda: fds.daily_dragon_tiger(), lambda d: d is None or isinstance(d, dict), "FDS", optional=True),
        case("north_money_realtime", "北向实时", lambda: fds.north_money_realtime(), lambda d: d is None or isinstance(d, list), "FDS", optional=True),
        case("fund_flow_baidu", "百度资金流", lambda: fds.fund_flow_baidu(SYMBOL, days=5), lambda d: d is None or isinstance(d, list), "FDS", optional=True),
        case("eastmoney_reports", "东财研报", lambda: fds.eastmoney_reports(SYMBOL, max_pages=1), lambda d: d is None or isinstance(d, list), "FDS", optional=True),
        case("cn_cpi", "CPI宏观", lambda: fds.cn_cpi(), lambda d: d is None or (isinstance(d, list) and (not d or isinstance(d[0], dict))), "FDS", optional=True),
        case("name_to_code", "名称转码", lambda: fds.name_to_code("贵州茅台"), lambda d: d and str(d).startswith("SH"), "FDS"),
        case("code_to_name", "代码转名", lambda: fds.code_to_name(SYMBOL), lambda d: isinstance(d, str) and len(d) > 0, "FDS"),
        case("get_status", "系统状态", lambda: fds.get_status(), lambda d: isinstance(d, dict) and "providers" in d, "FDS"),
        case("health_check", "健康检查", lambda: fds.health_check(), lambda d: isinstance(d, dict), "FDS"),
        case("intraday", "分时", lambda: fds.intraday(SYMBOL), lambda d: d is None or (isinstance(d, list) and (not d or isinstance(d[0], IntradayData))), "FDS", optional=True),
        case("iwencai", "问财", lambda: fds.iwencai("市盈率小于30"), lambda d: d is None or isinstance(d, list), "FDS", optional=True),
        case("valuation_percentiles", "估值分位bundle", lambda: fds.valuation_percentiles(SYMBOL, years=5), lambda d: d is None or isinstance(d, dict), "FDS", optional=True),
    ]
    if quick:
        ids = {
            "quote", "kline", "valuation", "tushare_daily", "announcement_list",
            "report_forecast", "search", "consensus_eps", "industry_comparison",
            "name_to_code", "valuation_calc", "get_status", "concept_blocks",
        }
        cases = [c for c in cases if c["id"] in ids]
    return cases


def run_verify(quick: bool) -> Dict[str, Any]:
    results = []
    passed = failed = skipped = 0
    for c in build_cases(quick):
        entry = {"id": c["id"], "name": c["name"], "origin": c["origin"], "optional": c.get("optional", False)}
        try:
            data = c["call"]()
            ok, msg = _ok(data, c["check"])
            if ok:
                entry["status"] = "pass"
                entry["detail"] = msg
                if isinstance(data, list) and data and isinstance(data[0], dict):
                    entry["sample_keys"] = list(data[0].keys())[:10]
                elif is_dataclass(data):
                    entry["sample"] = {k: getattr(data, k) for k in ("symbol", "current", "name", "source") if hasattr(data, k)}
                passed += 1
            elif c.get("optional"):
                entry["status"] = "skip"
                entry["detail"] = msg
                skipped += 1
            else:
                entry["status"] = "fail"
                entry["detail"] = msg
                failed += 1
        except Exception as e:
            entry["status"] = "skip" if c.get("optional") else "fail"
            entry["detail"] = f"{type(e).__name__}: {e}"
            if c.get("optional"):
                skipped += 1
            else:
                failed += 1
        results.append(entry)

    return {
        "timestamp": datetime.now().isoformat(),
        "symbol": SYMBOL,
        "quick": quick,
        "summary": {"pass": passed, "fail": failed, "skip": skipped, "total": len(results)},
        "results": results,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    report = run_verify(args.quick)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        s = report["summary"]
        print(f"Teak-FDS verify @ {report['timestamp']}")
        print(f"PASS {s['pass']}  FAIL {s['fail']}  SKIP {s['skip']}  TOTAL {s['total']}\n")
        for r in report["results"]:
            mark = {"pass": "✓", "fail": "✗", "skip": "○"}[r["status"]]
            print(f"  {mark} [{r['id']}] {r['name']} ({r['origin']}) — {r.get('detail', '')}")
    sys.exit(1 if report["summary"]["fail"] else 0)


if __name__ == "__main__":
    main()
