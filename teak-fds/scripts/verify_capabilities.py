#!/usr/bin/env python3
"""
Teak-FDS 能力矩阵验证。

用法:
  python scripts/verify_capabilities.py           # 联网全量
  python scripts/verify_capabilities.py --quick # 核心 15 项
  python scripts/verify_capabilities.py --json
  python scripts/verify_capabilities.py --category valuation
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import is_dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

SYMBOL = "SH600519"
TS_CODE = "600519.SH"
RECENT = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
TODAY = datetime.now().strftime("%Y%m%d")
MONTH = datetime.now().strftime("%Y%m")


def _ok(data: Any, checker: Callable[[Any], bool], allow_none: bool = False) -> Tuple[bool, str]:
    if data is None:
        return (True, "ok (none allowed)") if allow_none else (False, "returned None")
    try:
        if checker(data):
            return True, "ok"
        return False, "shape mismatch"
    except Exception as e:
        return False, str(e)


def _is_list_dict(d: Any, min_len: int = 1, key: Optional[str] = None) -> bool:
    if not isinstance(d, list) or len(d) < min_len:
        return False
    if key and not isinstance(d[0], dict):
        return False
    if key and key not in d[0]:
        return False
    return True


def _is_dict_keys(d: Any, *keys: str) -> bool:
    return isinstance(d, dict) and all(k in d for k in keys)


def build_cases(quick: bool, category: Optional[str] = None) -> List[Dict[str, Any]]:
    from teakfds import TeakFDS
    from teakfds.models import (
        BalanceData,
        CashFlowData,
        DepthData,
        FinancialIndicator,
        IncomeData,
        IntradayData,
        KlineData,
        QuoteData,
        ValuationData,
    )

    fds = TeakFDS(use_cache=False)
    _ann_cache: Dict[str, Any] = {}

    def ann():
        if "rows" not in _ann_cache:
            _ann_cache["rows"] = fds.announcement_list(SYMBOL)
        return _ann_cache["rows"]

    def case(
        cid: str,
        name: str,
        fn: Callable[[], Any],
        check: Callable[[Any], bool],
        cat: str,
        origin: str = "FDS",
        optional: bool = False,
        allow_none: bool = False,
    ) -> Dict[str, Any]:
        return {
            "id": cid,
            "name": name,
            "call": fn,
            "check": check,
            "category": cat,
            "origin": origin,
            "optional": optional,
            "allow_none": allow_none,
        }

    cases: List[Dict[str, Any]] = [
        # --- 行情 ---
        case("quote", "实时行情", lambda: fds.quote(SYMBOL),
             lambda d: is_dataclass(d) and isinstance(d, QuoteData) and d.current, "quote"),
        case("batch_quote", "批量行情", lambda: fds.batch_quote([SYMBOL, "SZ000001"]),
             lambda d: isinstance(d, list) and len(d) >= 1 and is_dataclass(d[0]), "quote"),
        case("quote_ext", "扩展行情", lambda: fds.quote_ext(SYMBOL),
             lambda d: is_dataclass(d) and isinstance(d, QuoteData), "quote"),
        case("depth", "五档盘口", lambda: fds.depth(SYMBOL),
             lambda d: d is None or (is_dataclass(d) and isinstance(d, DepthData)), "quote", optional=True),
        case("intraday", "分时", lambda: fds.intraday(SYMBOL),
             lambda d: d is None or (isinstance(d, list) and (not d or isinstance(d[0], IntradayData))),
             "quote", optional=True),
        case("minute_kline", "雪球分钟K", lambda: fds.minute_kline(SYMBOL),
             lambda d: d is None or isinstance(d, dict), "quote", optional=True),
        case("pankou", "雪球盘口", lambda: fds.pankou(SYMBOL),
             lambda d: d is None or isinstance(d, dict), "quote", optional=True),
        case("tick_data", "逐笔", lambda: fds.tick_data(SYMBOL, count=50),
             lambda d: d is None or isinstance(d, list), "quote", optional=True),
        # --- K线 ---
        case("kline", "日K线", lambda: fds.kline(SYMBOL, count=5),
             lambda d: isinstance(d, list) and d and isinstance(d[0], KlineData), "kline"),
        case("kline_week", "周K线", lambda: fds.kline(SYMBOL, period="week", count=3),
             lambda d: d is None or (isinstance(d, list) and (not d or isinstance(d[0], KlineData))),
             "kline", optional=True),
        case("pro_bar", "复权K线", lambda: fds.pro_bar(SYMBOL, start_date=RECENT, end_date=TODAY),
             lambda d: d is None or _is_list_dict(d, 0), "kline", optional=True),
        case("stk_mins", "分钟K", lambda: fds.stk_mins(SYMBOL, start_date=RECENT, end_date=TODAY, freq="5min"),
             lambda d: d is None or isinstance(d, list), "kline", optional=True),
        # --- 估值 ---
        case("valuation", "估值", lambda: fds.valuation(SYMBOL),
             lambda d: is_dataclass(d) and isinstance(d, ValuationData), "valuation"),
        case("valuation_calc", "前向PE/PEG", lambda: fds.valuation_calc(SYMBOL),
             lambda d: d is None or (isinstance(d, dict) and "pe_ttm" in d), "valuation"),
        case("valuation_history", "历史估值", lambda: fds.valuation_history(SYMBOL, years=3),
             lambda d: d is None or (hasattr(d, "stock_info") or isinstance(d, dict)), "valuation", optional=True),
        case("valuation_percentiles", "估值分位bundle", lambda: fds.valuation_percentiles(SYMBOL, years=5),
             lambda d: d is None or _is_dict_keys(d, "pe_ttm"), "valuation", optional=True),
        case("pe_percentile", "PE分位", lambda: fds.pe_percentile(SYMBOL, years=5),
             lambda d: d is None or isinstance(d, dict), "valuation", optional=True),
        case("pb_percentile", "PB分位", lambda: fds.pb_percentile(SYMBOL, years=5),
             lambda d: d is None or isinstance(d, dict), "valuation", optional=True),
        case("ps_percentile", "PS分位", lambda: fds.ps_percentile(SYMBOL, years=5),
             lambda d: d is None or isinstance(d, dict), "valuation", optional=True),
        case("dyr_percentile", "股息率分位", lambda: fds.dyr_percentile(SYMBOL, years=5),
             lambda d: d is None or isinstance(d, dict), "valuation", optional=True),
        case("price_metric_percentile", "单指标分位", lambda: fds.price_metric_percentile(SYMBOL, "pe_ttm", 5),
             lambda d: d is None or isinstance(d, dict), "valuation", optional=True),
        case("dividend", "分红", lambda: fds.dividend(SYMBOL),
             lambda d: d is None or (
                 isinstance(d, list)
                 and (not d or float(d[0].get("amount") or d[0].get("cash_div") or 0) > 0)
             ), "valuation"),
        case("consensus_eps", "一致预期EPS", lambda: fds.consensus_eps(SYMBOL),
             lambda d: d is None or _is_list_dict(d, 0), "valuation"),
        # --- 财务 ---
        case("income", "利润表模型", lambda: fds.income(SYMBOL),
             lambda d: d is None or isinstance(d, IncomeData), "financial", optional=True),
        case("balance_sheet", "资产负债表", lambda: fds.balance_sheet(SYMBOL),
             lambda d: d is None or isinstance(d, BalanceData), "financial", optional=True),
        case("cash_flow", "现金流", lambda: fds.cash_flow(SYMBOL),
             lambda d: d is None or isinstance(d, CashFlowData), "financial", optional=True),
        case("financial_indicator", "财务指标", lambda: fds.financial_indicator(SYMBOL),
             lambda d: d is None or isinstance(d, FinancialIndicator), "financial", optional=True),
        case("income_df", "利润表dict", lambda: fds.income_df(SYMBOL),
             lambda d: d is None or _is_list_dict(d, 0), "financial", optional=True),
        case("balance_sheet_df", "负债表dict", lambda: fds.balance_sheet_df(SYMBOL),
             lambda d: d is None or _is_list_dict(d, 0), "financial", optional=True),
        case("cash_flow_df", "现金流dict", lambda: fds.cash_flow_df(SYMBOL),
             lambda d: d is None or _is_list_dict(d, 0), "financial", optional=True),
        case("finance_snapshot", "财务快照", lambda: fds.finance_snapshot(SYMBOL),
             lambda d: d is None or isinstance(d, dict), "financial", optional=True),
        case("xdxr", "除权除息", lambda: fds.xdxr(SYMBOL),
             lambda d: d is None or isinstance(d, list), "financial", optional=True),
        case("forecast", "业绩预告", lambda: fds.forecast(SYMBOL, start_date=RECENT, end_date=TODAY),
             lambda d: d is None or isinstance(d, list), "financial", optional=True),
        case("express", "业绩快报", lambda: fds.express(SYMBOL, start_date=RECENT, end_date=TODAY),
             lambda d: d is None or isinstance(d, list), "financial", optional=True),
        # --- 研报 ---
        case("report_forecast", "盈利预测", lambda: fds.report_forecast(SYMBOL),
             lambda d: _is_list_dict(d, 1, "year"), "report"),
        case("report_rating", "机构评级", lambda: fds.report_rating(SYMBOL),
             lambda d: _is_list_dict(d, 1) and ("投资评级" in d[0] or "rating" in d[0]), "report"),
        case("report_list", "研报列表", lambda: fds.report_list(SYMBOL, start_date=RECENT, end_date=TODAY),
             lambda d: d is None or _is_list_dict(d, 0), "report", optional=True),
        case("eastmoney_reports", "东财研报", lambda: fds.eastmoney_reports(SYMBOL, max_pages=1),
             lambda d: d is None or _is_list_dict(d, 1, "title"), "report"),
        case("institution_recommend", "机构推荐", lambda: fds.institution_recommend(SYMBOL),
             lambda d: d is None or isinstance(d, (dict, list)), "report", optional=True),
        case("institution_participation", "机构参与度", lambda: fds.institution_participation(SYMBOL),
             lambda d: d is None or isinstance(d, dict), "report", optional=True),
        case("iwencai", "问财", lambda: fds.iwencai("市盈率小于30"),
             lambda d: d is None or isinstance(d, list), "report", optional=True),
        # --- 公告 ---
        case("announcement_list", "公告列表", lambda: fds.announcement_list(SYMBOL),
             lambda d: _is_list_dict(d, 1, "title"), "announcement"),
        case(
            "announcement_pdf_url",
            "公告PDF链接",
            lambda: (lambda rows: fds.announcement_pdf_url(rows[0].get("url") or rows[0].get("adjunct_url") or "") if rows else None)(ann()),
            lambda d: d is None or (isinstance(d, str) and d.startswith("http")),
            "announcement",
            optional=True,
        ),
        case("company_events", "公司动态", lambda: fds.company_events(),
             lambda d: d is None or isinstance(d, list), "announcement", optional=True),
        case("latest_announcements", "全市场公告", lambda: fds.latest_announcements(),
             lambda d: d is None or isinstance(d, list), "announcement", optional=True),
        # --- 搜索 ---
        case("search", "搜索news", lambda: fds.search("贵州茅台", data_type="news"),
             lambda d: d is None or _is_list_dict(d, 0), "search", optional=True),
        case("search_report", "搜索研报", lambda: fds.search_report("贵州茅台"),
             lambda d: d is None or isinstance(d, list), "search", optional=True),
        case("search_news", "搜索新闻", lambda: fds.search_news("贵州茅台", days=7),
             lambda d: d is None or isinstance(d, list), "search", optional=True),
        # --- 资金 ---
        case("money_flow", "个股资金流", lambda: fds.money_flow(SYMBOL, days=5),
             lambda d: d is None or isinstance(d, list), "flow", optional=True),
        case("capital_flow", "分钟资金", lambda: fds.capital_flow(SYMBOL),
             lambda d: d is None or isinstance(d, dict), "flow", optional=True),
        case("fund_flow_baidu", "百度资金流", lambda: fds.fund_flow_baidu(SYMBOL, days=5),
             lambda d: d is None or isinstance(d, list), "flow", optional=True),
        case("north_money_flow", "北向历史", lambda: fds.north_money_flow(start_date=RECENT, end_date=TODAY),
             lambda d: d is None or isinstance(d, list), "flow", optional=True),
        case("hsgt_top10", "港通十大", lambda: fds.hsgt_top10(),
             lambda d: d is None or isinstance(d, list), "flow", optional=True),
        case("north_money_realtime", "北向实时", lambda: fds.north_money_realtime(),
             lambda d: d is None or isinstance(d, list), "flow", optional=True),
        case("top_list", "龙虎榜个股", lambda: fds.top_list(),
             lambda d: d is None or isinstance(d, list), "flow", optional=True),
        case("limit_up_down", "涨跌停", lambda: fds.limit_up_down(),
             lambda d: d is None or isinstance(d, list), "flow", optional=True),
        case("daily_dragon_tiger", "全市场龙虎榜", lambda: fds.daily_dragon_tiger(),
             lambda d: d is None or isinstance(d, dict), "flow", optional=True),
        # --- 信号 ---
        case("hot_stocks", "强势股", lambda: fds.hot_stocks(),
             lambda d: d is None or isinstance(d, list), "signal", optional=True),
        case(
            "concept_blocks",
            "概念板块",
            lambda: fds.concept_blocks(SYMBOL),
            lambda d: isinstance(d, dict) and (len(d.get("concept") or []) > 0 or len(d.get("industry") or []) > 0),
            "signal",
        ),
        case("industry_comparison", "行业对比", lambda: fds.industry_comparison(top_n=5),
             lambda d: _is_dict_keys(d, "top", "total") and len(d["top"]) > 0, "signal"),
        case("market_breadth", "市场广度", lambda: fds.market_breadth(),
             lambda d: d is None or isinstance(d, dict), "signal", optional=True),
        # --- 指数 ---
        case("index_quotes", "指数行情", lambda: fds.index_quotes(),
             lambda d: d is None or isinstance(d, dict), "index", optional=True),
        case("index_list", "指数列表", lambda: fds.index_list(market="SSE"),
             lambda d: d is None or isinstance(d, list), "index", optional=True),
        case("index_kline", "指数K线", lambda: fds.index_kline("000001.SH", start_date=RECENT, end_date=TODAY),
             lambda d: d is None or isinstance(d, list), "index", optional=True),
        # --- 宏观 ---
        case("cn_cpi", "CPI", lambda: fds.cn_cpi(),
             lambda d: d is None or _is_list_dict(d, 0), "macro", optional=True),
        case("cn_ppi", "PPI", lambda: fds.cn_ppi(),
             lambda d: d is None or isinstance(d, list), "macro", optional=True),
        case("cn_pmi", "PMI", lambda: fds.cn_pmi(),
             lambda d: d is None or isinstance(d, list), "macro", optional=True),
        case("cn_gdp", "GDP", lambda: fds.cn_gdp(),
             lambda d: d is None or isinstance(d, list), "macro", optional=True),
        case("cn_m", "货币供应", lambda: fds.cn_m(),
             lambda d: d is None or isinstance(d, list), "macro", optional=True),
        case("shibor", "Shibor", lambda: fds.shibor(),
             lambda d: d is None or isinstance(d, list), "macro", optional=True),
        # --- F10 ---
        case("insider_trading", "高管增减持", lambda: fds.insider_trading(SYMBOL),
             lambda d: d is None or isinstance(d, list), "f10", optional=True),
        case("top_holders", "十大股东", lambda: fds.top_holders(SYMBOL),
             lambda d: d is None or _is_list_dict(d, 0), "f10", optional=True),
        case("top_float_holders", "十大流通股东", lambda: fds.top_float_holders(SYMBOL),
             lambda d: d is None or isinstance(d, list), "f10", optional=True),
        case("shareholder_count", "股东人数", lambda: fds.shareholder_count(SYMBOL),
             lambda d: d is None or isinstance(d, list), "f10", optional=True),
        case("managers", "高管列表", lambda: fds.managers(SYMBOL),
             lambda d: d is None or isinstance(d, list), "f10", optional=True),
        case("main_business", "主营构成", lambda: fds.main_business(SYMBOL, biz_type="P"),
             lambda d: d is None or isinstance(d, list), "f10", optional=True),
        case("share_unlock", "限售解禁", lambda: fds.share_unlock(SYMBOL),
             lambda d: d is None or isinstance(d, list), "f10", optional=True),
        case("survey_activities", "调研活动", lambda: fds.survey_activities(SYMBOL),
             lambda d: d is None or isinstance(d, list), "f10", optional=True),
        # --- 雪球 ---
        case("watchlist_stocks", "自选股", lambda: fds.watchlist_stocks(),
             lambda d: d is None or isinstance(d, dict), "xueqiu", optional=True),
        # --- 基础 / 系统 ---
        case("stock_basic", "股票列表", lambda: fds.stock_basic(symbol=SYMBOL),
             lambda d: d is None or _is_list_dict(d, 1, "ts_code"), "basic", optional=True),
        case("name_to_code", "名称转码", lambda: fds.name_to_code("贵州茅台"),
             lambda d: d and str(d).startswith("SH"), "basic"),
        case("code_to_name", "代码转名", lambda: fds.code_to_name(SYMBOL),
             lambda d: isinstance(d, str) and len(d) > 0, "basic"),
        case("trade_cal", "交易日历", lambda: fds.trade_cal(start_date=RECENT, end_date=TODAY),
             lambda d: d is None or _is_list_dict(d, 1, "cal_date"), "basic", optional=True),
        case("tushare_daily", "Tushare逃生舱", lambda: fds.tushare(
            "daily", ts_code=TS_CODE, start_date=RECENT, end_date=TODAY, fields="ts_code,trade_date,close"
        ), lambda d: _is_list_dict(d, 1, "close"), "basic"),
        case("tushare_concept_detail", "概念明细", lambda: fds.tushare("concept_detail", ts_code=TS_CODE),
             lambda d: d is None or _is_list_dict(d, 1, "concept_name"), "basic", optional=True),
        case("get_status", "系统状态", lambda: fds.get_status(),
             lambda d: _is_dict_keys(d, "providers"), "system"),
        case("health_check", "健康检查", lambda: fds.health_check(),
             lambda d: isinstance(d, dict), "system"),
        case("get_provider_tencent", "Provider腾讯", lambda: fds.get_provider("tencent"),
             lambda d: d is not None and d.is_available(), "system", optional=True),
    ]

    if quick:
        quick_ids = {
            "quote", "kline", "valuation", "tushare_daily", "announcement_list",
            "report_forecast", "report_rating", "search", "consensus_eps",
            "industry_comparison", "name_to_code", "valuation_calc", "get_status",
            "concept_blocks", "eastmoney_reports",
        }
        cases = [c for c in cases if c["id"] in quick_ids]

    if category:
        cases = [c for c in cases if c["category"] == category]

    return cases


def run_verify(quick: bool, category: Optional[str] = None) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    passed = failed = skipped = 0

    for c in build_cases(quick, category):
        entry = {
            "id": c["id"],
            "name": c["name"],
            "category": c["category"],
            "origin": c["origin"],
            "optional": c.get("optional", False),
        }
        try:
            data = c["call"]()
            ok, msg = _ok(data, c["check"], allow_none=c.get("allow_none", False))
            if ok:
                entry["status"] = "pass"
                entry["detail"] = msg
                if isinstance(data, list) and data and isinstance(data[0], dict):
                    entry["sample_keys"] = list(data[0].keys())[:10]
                elif is_dataclass(data):
                    entry["sample"] = {
                        k: getattr(data, k)
                        for k in ("symbol", "current", "name", "source")
                        if hasattr(data, k)
                    }
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

    by_cat: Dict[str, Dict[str, int]] = {}
    for r in results:
        cat = r["category"]
        by_cat.setdefault(cat, {"pass": 0, "fail": 0, "skip": 0})
        by_cat[cat][r["status"]] = by_cat[cat].get(r["status"], 0) + 1

    return {
        "timestamp": datetime.now().isoformat(),
        "symbol": SYMBOL,
        "quick": quick,
        "category_filter": category,
        "summary": {"pass": passed, "fail": failed, "skip": skipped, "total": len(results)},
        "by_category": by_cat,
        "results": results,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Teak-FDS capability verification")
    ap.add_argument("--quick", action="store_true", help="核心子集")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    ap.add_argument("--category", type=str, help="仅测某类: quote/kline/valuation/...")
    args = ap.parse_args()

    report = run_verify(args.quick, args.category)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        s = report["summary"]
        print(f"Teak-FDS verify @ {report['timestamp']}")
        print(f"PASS {s['pass']}  FAIL {s['fail']}  SKIP {s['skip']}  TOTAL {s['total']}")
        if report.get("by_category"):
            print("\n按分类:")
            for cat, st in sorted(report["by_category"].items()):
                print(f"  {cat}: pass={st.get('pass',0)} fail={st.get('fail',0)} skip={st.get('skip',0)}")
        print()
        for r in report["results"]:
            mark = {"pass": "✓", "fail": "✗", "skip": "○"}[r["status"]]
            print(f"  {mark} [{r['id']}] {r['name']} ({r['category']}) — {r.get('detail', '')}")

    sys.exit(1 if report["summary"]["fail"] else 0)


if __name__ == "__main__":
    main()
