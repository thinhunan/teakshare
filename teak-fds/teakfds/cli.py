#!/usr/bin/env python3
"""
FinanceDataSource CLI - 命令行接口

Usage:
    fds quote SH600519
    fds valuation SZ000858
    fds pe-percentile 600519 --years 10
    fds kline SH600519 --period day --count 30
    fds income SH600519
    fds search "贵州茅台" --type news

Version: 1.0.0
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Any, List, Dict

from teakfds.finance_data_source import FinanceDataSource


class CLIOutput:
    """CLI 输出格式化器"""

    @staticmethod
    def format_value(value: Any, precision: int = 2) -> str:
        """格式化数值"""
        if value is None:
            return "-"
        if isinstance(value, float):
            return f"{value:.{precision}f}"
        return str(value)

    @staticmethod
    def print_header(title: str):
        """打印标题头"""
        print(f"\n{'='*50}")
        print(f" {title}")
        print(f"{'='*50}")

    @staticmethod
    def print_kv(key: str, value: Any, unit: str = "", precision: int = 2):
        """打印键值对"""
        formatted = CLIOutput.format_value(value, precision)
        if unit and value is not None:
            formatted = f"{formatted}{unit}"
        print(f"  {key}: {formatted}")

    @staticmethod
    def print_table(headers: List[str], rows: List[List[Any]], precision: int = 2):
        """打印表格"""
        if not rows:
            print("  (无数据)")
            return

        # 计算列宽
        widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                cell_str = CLIOutput.format_value(cell, precision) if isinstance(cell, float) else str(cell) if cell is not None else "-"
                widths[i] = max(widths[i], len(cell_str))

        # 打印表头
        header_line = "  " + " | ".join(h.ljust(w) for h, w in zip(headers, widths))
        print(header_line)
        print("  " + "-+-".join("-" * w for w in widths))

        # 打印数据行
        for row in rows:
            cells = []
            for i, cell in enumerate(row):
                if isinstance(cell, float):
                    cells.append(CLIOutput.format_value(cell, precision).ljust(widths[i]))
                elif cell is None:
                    cells.append("-".ljust(widths[i]))
                else:
                    cells.append(str(cell).ljust(widths[i]))
            print("  " + " | ".join(cells))

    @staticmethod
    def to_json(data: Any) -> str:
        """转换为 JSON 字符串"""
        if hasattr(data, 'to_dict'):
            return json.dumps(data.to_dict(), ensure_ascii=False, indent=2)
        elif isinstance(data, dict):
            return json.dumps(data, ensure_ascii=False, indent=2)
        elif isinstance(data, list):
            items = [item.to_dict() if hasattr(item, 'to_dict') else item for item in data]
            return json.dumps(items, ensure_ascii=False, indent=2)
        return str(data)


class FDSCommands:
    """FDS CLI 命令实现"""

    def __init__(self):
        self.fds = FinanceDataSource()

    # ========== 行情命令 ==========

    def quote(self, symbol: str, json_output: bool = False):
        """获取实时行情"""
        data = self.fds.quote(symbol)
        if not data:
            print(f"错误: 无法获取 {symbol} 的行情数据")
            return 1

        if json_output:
            print(CLIOutput.to_json(data))
            return 0

        CLIOutput.print_header(f"{data.name} ({data.symbol}) 实时行情")
        CLIOutput.print_kv("当前价", data.current, "元")
        CLIOutput.print_kv("涨跌幅", data.percent, "%")
        CLIOutput.print_kv("开盘价", data.open, "元")
        CLIOutput.print_kv("最高价", data.high, "元")
        CLIOutput.print_kv("最低价", data.low, "元")
        CLIOutput.print_kv("昨收价", data.close, "元")
        CLIOutput.print_kv("成交量", data.volume, "股")
        CLIOutput.print_kv("成交额", data.amount, "元")
        CLIOutput.print_kv("更新时间", data.timestamp)
        CLIOutput.print_kv("数据来源", data.source)
        return 0

    def batch_quote(self, symbols: List[str], json_output: bool = False):
        """批量获取行情"""
        data = self.fds.batch_quote(symbols)
        if not data:
            print("错误: 无法获取行情数据")
            return 1

        if json_output:
            print(CLIOutput.to_json(data))
            return 0

        CLIOutput.print_header("批量行情")
        headers = ["代码", "名称", "现价", "涨跌幅%", "成交量", "成交额"]
        rows = [[q.symbol, q.name, q.current, q.percent, q.volume, q.amount] for q in data]
        CLIOutput.print_table(headers, rows)
        return 0

    def depth(self, symbol: str, json_output: bool = False):
        """获取盘口数据"""
        data = self.fds.depth(symbol)
        if not data:
            print(f"错误: 无法获取 {symbol} 的盘口数据")
            return 1

        if json_output:
            print(CLIOutput.to_json(data))
            return 0

        CLIOutput.print_header(f"{symbol} 盘口数据")
        print("\n  买盘:")
        print(f"    买五: {data.bid5:.2f} × {data.bid_vol5}")
        print(f"    买四: {data.bid4:.2f} × {data.bid_vol4}")
        print(f"    买三: {data.bid3:.2f} × {data.bid_vol3}")
        print(f"    买二: {data.bid2:.2f} × {data.bid_vol2}")
        print(f"    买一: {data.bid1:.2f} × {data.bid_vol1}")

        print("\n  卖盘:")
        print(f"    卖一: {data.ask1:.2f} × {data.ask_vol1}")
        print(f"    卖二: {data.ask2:.2f} × {data.ask_vol2}")
        print(f"    卖三: {data.ask3:.2f} × {data.ask_vol3}")
        print(f"    卖四: {data.ask4:.2f} × {data.ask_vol4}")
        print(f"    卖五: {data.ask5:.2f} × {data.ask_vol5}")
        return 0

    def kline(self, symbol: str, period: str = 'day', count: int = 30, json_output: bool = False):
        """获取K线数据"""
        data = self.fds.kline(symbol, period=period, count=count)
        if not data:
            print(f"错误: 无法获取 {symbol} 的K线数据")
            return 1

        if json_output:
            print(CLIOutput.to_json(data))
            return 0

        period_names = {'day': '日线', 'week': '周线', 'month': '月线'}
        CLIOutput.print_header(f"{symbol} {period_names.get(period, period)}K线 (最近{count}条)")

        headers = ["日期", "开盘", "最高", "最低", "收盘", "成交量", "成交额"]
        rows = [[k.date, k.open, k.high, k.low, k.close, k.volume, k.amount] for k in data[-10:]]
        CLIOutput.print_table(headers, rows)
        print(f"\n  ... 共 {len(data)} 条记录")
        return 0

    # ========== 估值命令 ==========

    def valuation(self, symbol: str, json_output: bool = False):
        """获取估值数据"""
        data = self.fds.valuation(symbol)
        if not data:
            print(f"错误: 无法获取 {symbol} 的估值数据")
            return 1

        if json_output:
            print(CLIOutput.to_json(data))
            return 0

        CLIOutput.print_header(f"{data.name} ({data.symbol}) 估值数据")
        CLIOutput.print_kv("PE-TTM", data.pe_ttm)
        CLIOutput.print_kv("PE-LYR", data.pe_lyr)
        CLIOutput.print_kv("PB", data.pb)
        CLIOutput.print_kv("PS-TTM", data.ps_ttm)
        dy_pct = data.dividend_yield * 100 if data.dividend_yield is not None else None
        CLIOutput.print_kv("股息率", dy_pct, "%")
        CLIOutput.print_kv("市值", data.market_cap, "亿")
        return 0

    def pe_percentile(self, symbol: str, years: int = 10, json_output: bool = False):
        """获取PE历史分位"""
        data = self.fds.pe_percentile(symbol, years=years)
        if not data:
            print(f"错误: 无法获取 {symbol} 的PE分位数据")
            return 1

        if json_output:
            print(CLIOutput.to_json(data))
            return 0

        CLIOutput.print_header(f"{symbol} PE历史分位 ({years}年)")
        CLIOutput.print_kv("当前PE", data['current'])
        CLIOutput.print_kv("历史分位", data['percentile'], "%")

        # 判断估值区间
        pct = data['percentile']
        if pct <= 20:
            level = "低估区 📉"
        elif pct <= 40:
            level = "偏低区"
        elif pct <= 60:
            level = "合理区"
        elif pct <= 80:
            level = "偏高区"
        else:
            level = "高估区 📈"
        print(f"  估值水平: {level}")

        print()
        CLIOutput.print_kv("20%分位(低估线)", data['percentile_20'])
        CLIOutput.print_kv("50%分位(中位数)", data['percentile_50'])
        CLIOutput.print_kv("80%分位(高估线)", data['percentile_80'])
        CLIOutput.print_kv("历史最高", data['max'])
        CLIOutput.print_kv("历史最低", data['min'])
        CLIOutput.print_kv("历史平均", data['avg'])
        return 0

    def pb_percentile(self, symbol: str, years: int = 10, json_output: bool = False):
        """获取PB历史分位"""
        data = self.fds.pb_percentile(symbol, years=years)
        if not data:
            print(f"错误: 无法获取 {symbol} 的PB分位数据")
            return 1

        if json_output:
            print(CLIOutput.to_json(data))
            return 0

        CLIOutput.print_header(f"{symbol} PB历史分位 ({years}年)")
        CLIOutput.print_kv("当前PB", data['current'])
        CLIOutput.print_kv("历史分位", data['percentile'], "%")

        # 判断估值区间
        pct = data['percentile']
        if pct <= 20:
            level = "低估区 📉"
        elif pct <= 40:
            level = "偏低区"
        elif pct <= 60:
            level = "合理区"
        elif pct <= 80:
            level = "偏高区"
        else:
            level = "高估区 📈"
        print(f"  估值水平: {level}")

        print()
        CLIOutput.print_kv("20%分位(低估线)", data['percentile_20'])
        CLIOutput.print_kv("50%分位(中位数)", data['percentile_50'])
        CLIOutput.print_kv("80%分位(高估线)", data['percentile_80'])
        CLIOutput.print_kv("历史最高", data['max'])
        CLIOutput.print_kv("历史最低", data['min'])
        CLIOutput.print_kv("历史平均", data['avg'])
        return 0

    def ps_percentile(self, symbol: str, years: int = 10, json_output: bool = False):
        """获取PS-TTM历史分位"""
        data = self.fds.ps_percentile(symbol, years=years)
        if not data:
            print(f"错误: 无法获取 {symbol} 的PS分位数据")
            return 1
        if json_output:
            print(CLIOutput.to_json(data))
            return 0
        CLIOutput.print_header(f"{symbol} PS-TTM历史分位 ({years}年)")
        CLIOutput.print_kv("当前PS", data['current'])
        CLIOutput.print_kv("历史分位", data['percentile'], "%")
        print()
        CLIOutput.print_kv("20%分位", data['percentile_20'])
        CLIOutput.print_kv("50%分位", data['percentile_50'])
        CLIOutput.print_kv("80%分位", data['percentile_80'])
        CLIOutput.print_kv("历史最高", data['max'])
        CLIOutput.print_kv("历史最低", data['min'])
        CLIOutput.print_kv("历史平均", data['avg'])
        return 0

    def dyr_percentile(self, symbol: str, years: int = 10, json_output: bool = False):
        """获取股息率历史分位"""
        data = self.fds.dyr_percentile(symbol, years=years)
        if not data:
            print(f"错误: 无法获取 {symbol} 的股息率分位数据")
            return 1
        if json_output:
            print(CLIOutput.to_json(data))
            return 0
        CLIOutput.print_header(f"{symbol} 股息率历史分位 ({years}年)")
        CLIOutput.print_kv("当前股息率", data['current'], "%")
        CLIOutput.print_kv("历史分位", data['percentile'], "%")
        print()
        CLIOutput.print_kv("20%分位", data['percentile_20'])
        CLIOutput.print_kv("50%分位", data['percentile_50'])
        CLIOutput.print_kv("80%分位", data['percentile_80'])
        CLIOutput.print_kv("历史最高", data['max'])
        CLIOutput.print_kv("历史最低", data['min'])
        CLIOutput.print_kv("历史平均", data['avg'])
        return 0

    def valuation_percentiles_cmd(self, symbol: str, years: int = 10, json_output: bool = False):
        """一次输出 PE/PB/PS/股息率 分位"""
        data = self.fds.valuation_percentiles(symbol, years=years)
        if not data:
            print(f"错误: 无法获取 {symbol} 的估值得分位 bundle")
            return 1
        if json_output:
            print(CLIOutput.to_json(data))
            return 0
        CLIOutput.print_header(f"{symbol} 估值得分位 ({data.get('granularity', '')}, {years}年窗口)")
        for label, key in (
            ("PE-TTM", "pe_ttm"),
            ("PB", "pb"),
            ("PS-TTM", "ps_ttm"),
            ("股息率", "dyr"),
        ):
            block = data.get(key) or {}
            print(f"\n  [{label}]")
            CLIOutput.print_kv("  当前值", block.get("current"))
            CLIOutput.print_kv("  历史分位", block.get("percentile"), "%")
            CLIOutput.print_kv("  20%分位", block.get("percentile_20"))
            CLIOutput.print_kv("  50%分位", block.get("percentile_50"))
            CLIOutput.print_kv("  80%分位", block.get("percentile_80"))
            CLIOutput.print_kv("  历史最高", block.get("max"))
            CLIOutput.print_kv("  历史最低", block.get("min"))
            CLIOutput.print_kv("  历史平均", block.get("avg"))
        return 0

    def dividend(self, symbol: str, json_output: bool = False):
        """获取分红数据"""
        data = self.fds.dividend(symbol)
        if not data:
            print(f"错误: 无法获取 {symbol} 的分红数据")
            return 1

        if json_output:
            print(CLIOutput.to_json(data))
            return 0

        CLIOutput.print_header(f"{symbol} 分红送股")
        headers = ["报告期", "公告日", "进度", "每股分红", "送股"]
        rows = [
            [
                d.get("end_date"),
                d.get("ann_date"),
                d.get("div_proc"),
                d.get("cash_div"),
                d.get("stk_div"),
            ]
            for d in data[:10]
        ]
        CLIOutput.print_table(headers, rows)
        return 0

    # ========== 财务命令 ==========

    def income(self, symbol: str, json_output: bool = False):
        """获取利润表"""
        data = self.fds.income(symbol)
        if not data:
            print(f"错误: 无法获取 {symbol} 的利润表")
            return 1

        if json_output:
            print(CLIOutput.to_json(data))
            return 0

        CLIOutput.print_header(f"{symbol} 利润表 (最新)")
        CLIOutput.print_kv("报告期", data.period)
        CLIOutput.print_kv("营业收入", data.revenue, "元")
        CLIOutput.print_kv("营业利润", data.operate_profit, "元")
        CLIOutput.print_kv("利润总额", data.total_profit, "元")
        CLIOutput.print_kv("净利润", data.net_profit, "元")
        CLIOutput.print_kv("归母净利润", data.net_profit_attr, "元")
        CLIOutput.print_kv("每股收益", data.eps, "元")
        return 0

    def balance(self, symbol: str, json_output: bool = False):
        """获取资产负债表"""
        data = self.fds.balance_sheet(symbol)
        if not data:
            print(f"错误: 无法获取 {symbol} 的资产负债表")
            return 1

        if json_output:
            print(CLIOutput.to_json(data))
            return 0

        CLIOutput.print_header(f"{symbol} 资产负债表 (最新)")
        CLIOutput.print_kv("报告期", data.period)
        CLIOutput.print_kv("总资产", data.total_assets, "元")
        CLIOutput.print_kv("总负债", data.total_liab, "元")
        CLIOutput.print_kv("股东权益", data.total_equity, "元")
        CLIOutput.print_kv("归母股东权益", data.total_equity_attr, "元")
        CLIOutput.print_kv("流动资产", data.current_assets, "元")
        CLIOutput.print_kv("流动负债", data.current_liab, "元")
        return 0

    def cashflow(self, symbol: str, json_output: bool = False):
        """获取现金流量表"""
        data = self.fds.cash_flow(symbol)
        if not data:
            print(f"错误: 无法获取 {symbol} 的现金流量表")
            return 1

        if json_output:
            print(CLIOutput.to_json(data))
            return 0

        CLIOutput.print_header(f"{symbol} 现金流量表 (最新)")
        CLIOutput.print_kv("报告期", data.period)
        CLIOutput.print_kv("经营活动现金流", data.n_cashflow_act, "元")
        CLIOutput.print_kv("投资活动现金流", data.n_cashflow_inv_act, "元")
        CLIOutput.print_kv("筹资活动现金流", data.n_cash_flows_fnc_act, "元")
        CLIOutput.print_kv("自由现金流", data.free_cashflow, "元")
        return 0

    def indicator(self, symbol: str, json_output: bool = False):
        """获取财务指标"""
        data = self.fds.financial_indicator(symbol)
        if not data:
            print(f"错误: 无法获取 {symbol} 的财务指标")
            return 1

        if json_output:
            print(CLIOutput.to_json(data))
            return 0

        CLIOutput.print_header(f"{symbol} 财务指标 (最新)")
        CLIOutput.print_kv("报告期", data.period)
        CLIOutput.print_kv("ROE", data.roe, "%")
        CLIOutput.print_kv("ROA", data.roa, "%")
        CLIOutput.print_kv("毛利率", data.gross_margin, "%")
        CLIOutput.print_kv("净利率", data.net_margin, "%")
        CLIOutput.print_kv("资产负债率", data.debt_ratio, "%")
        CLIOutput.print_kv("流动比率", data.current_ratio)
        CLIOutput.print_kv("速动比率", data.quick_ratio)
        return 0

    # ========== 资金流向命令 ==========

    def money_flow(self, symbol: str, days: int = 5, json_output: bool = False):
        """获取资金流向"""
        data = self.fds.money_flow(symbol, days=days)
        if not data:
            print(f"错误: 无法获取 {symbol} 的资金流向数据")
            return 1

        if json_output:
            print(CLIOutput.to_json(data))
            return 0

        CLIOutput.print_header(f"{symbol} 资金流向 (最近{days}天)")
        headers = ["日期", "主力净流入", "涨跌幅%", "超大单", "大单"]
        rows = [
            [
                d.get("trade_date") or d.get("date"),
                d.get("main_net", d.get("net_mf_amount")),
                d.get("change_pct"),
                d.get("buy_elg_amount", d.get("superNetIn")),
                d.get("buy_lg_amount", d.get("largeNetIn")),
            ]
            for d in data
        ]
        CLIOutput.print_table(headers, rows)
        return 0

    def north_flow(self, days: int = 10, json_output: bool = False):
        """获取北向资金"""
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days*2)).strftime('%Y%m%d')
        data = self.fds.north_money_flow(start_date=start_date, end_date=end_date)

        if data is None or (isinstance(data, list) and not data) or (
            hasattr(data, 'empty') and data.empty
        ):
            print("错误: 无法获取北向资金数据")
            return 1

        if json_output:
            if hasattr(data, 'to_dict'):
                print(json.dumps(data.to_dict(orient='records'), ensure_ascii=False, indent=2))
            else:
                print(CLIOutput.to_json(data))
            return 0

        CLIOutput.print_header(f"北向资金流向 (最近{days}天)")
        slice_rows = data[:days] if isinstance(data, list) else (
            data.head(days) if hasattr(data, "head") else []
        )
        headers = ['日期', '沪股通(亿)', '深股通(亿)', '北向合计(亿)']
        rows_out = []
        if isinstance(slice_rows, list):
            for row in slice_rows:
                rows_out.append([
                    str(row.get('trade_date', '')),
                    row.get('sh_amt', 0),
                    row.get('sz_amt', 0),
                    row.get('north_amt', 0)
                ])
        else:
            for _, row in slice_rows.iterrows():
                rows_out.append([
                    str(row.get('trade_date', '')),
                    row.get('sh_amt', 0),
                    row.get('sz_amt', 0),
                    row.get('north_amt', 0)
                ])
        CLIOutput.print_table(headers, rows_out)
        return 0

    # ========== 补充数据源命令 (V2) ==========

    def hot_stocks(self, date: str = None, json_output: bool = False):
        """当日强势股 + 题材归因"""
        data = self.fds.hot_stocks(date)
        if not data:
            print(f"错误: 无法获取强势股数据 (date={date or '今天'})")
            return 1

        if json_output:
            print(CLIOutput.to_json(data))
            return 0

        CLIOutput.print_header(f"当日强势股 ({date or '今天'}) 共 {len(data)} 只")
        headers = ["代码", "名称", "涨幅%", "换手%", "题材归因"]
        rows = [[d.get("code"), d.get("name"), d.get("change_pct"),
                 d.get("turnover_pct"), (d.get("reason") or "")[:40]] for d in data[:30]]
        CLIOutput.print_table(headers, rows)
        if len(data) > 30:
            print(f"\n  ... 共 {len(data)} 只 (仅显示前30)")
        return 0

    def concept_blocks(self, symbol: str, json_output: bool = False):
        """个股概念板块归属"""
        data = self.fds.concept_blocks(symbol)
        if not data:
            print(f"错误: 无法获取 {symbol} 的概念板块")
            return 1

        if json_output:
            print(CLIOutput.to_json(data))
            return 0

        CLIOutput.print_header(f"{symbol} 概念板块归属")
        print("\n  行业:")
        for b in data.get("industry", []):
            print(f"    {b['name']} ({b.get('change_pct', '-')}%)")
        print("\n  概念:")
        tags = data.get("concept_tags", [])
        for i in range(0, len(tags), 5):
            chunk = tags[i:i+5]
            print(f"    {', '.join(chunk)}")
        print("\n  地域:")
        for b in data.get("region", []):
            print(f"    {b['name']}")
        return 0

    def dragon_tiger_market(self, date: str = None, min_net_buy: float = None, json_output: bool = False):
        """全市场龙虎榜"""
        data = self.fds.daily_dragon_tiger(date, min_net_buy)
        if not data or not data.get("stocks"):
            print(f"错误: 无法获取龙虎榜数据 (date={date or '今天'})")
            if data and data.get("note"):
                print(f"  {data['note']}")
            return 1

        if json_output:
            print(CLIOutput.to_json(data))
            return 0

        suffix = f" (净买>{min_net_buy}万)" if min_net_buy else ""
        CLIOutput.print_header(f"{data['date']} 全市场龙虎榜{suffix} 共 {data['total_records']} 条")
        headers = ["代码", "名称", "涨跌%", "净买(万)", "买入(万)", "卖出(万)", "原因"]
        rows = [[s["code"], s["name"], s["change_pct"], s["net_buy_wan"],
                 s["buy_wan"], s["sell_wan"], (s.get("reason") or "")[:30]]
                for s in data["stocks"][:20]]
        CLIOutput.print_table(headers, rows)
        if data["total_records"] > 20:
            print(f"\n  ... 共 {data['total_records']} 条 (仅显示前20)")
        return 0

    def industry_compare(self, top_n: int = 20, json_output: bool = False):
        """行业涨跌排名"""
        data = self.fds.industry_comparison(top_n)
        if not data:
            print("错误: 无法获取行业对比数据")
            return 1

        if json_output:
            print(CLIOutput.to_json(data))
            return 0

        CLIOutput.print_header(f"行业涨跌排名 (共 {data['total']} 个行业)")
        print(f"\n  TOP {min(top_n, 10)} 涨幅:")
        headers = ["排名", "行业", "涨跌%", "成交额(亿)", "涨家数", "跌家数", "领涨股"]
        rows = [[r["rank"], r["name"], r["change_pct"], r.get("turnover_yi", "-"),
                 r.get("up_count", "-"), r.get("down_count", "-"), r.get("leader", "")]
                for r in data["top"][:10]]
        CLIOutput.print_table(headers, rows)
        print(f"\n  BOTTOM 5 跌幅:")
        rows_b = [[r["rank"], r["name"], r["change_pct"], r.get("turnover_yi", "-"),
                   r.get("up_count", "-"), r.get("down_count", "-"), r.get("leader", "")]
                  for r in data["bottom"][-5:]]
        CLIOutput.print_table(headers, rows_b)
        return 0

    def north_realtime(self, json_output: bool = False):
        """北向资金实时分钟流向"""
        data = self.fds.north_money_realtime()
        if not data:
            print("错误: 无法获取北向实时数据")
            return 1

        if json_output:
            print(CLIOutput.to_json(data))
            return 0

        valid = [r for r in data if r.get("hgt_yi") is not None]
        if not valid:
            print("暂无北向资金数据")
            return 0

        last = valid[-1]
        hgt = last.get("hgt_yi", 0)
        sgt = last.get("sgt_yi", 0)
        total = (hgt or 0) + (sgt or 0)

        CLIOutput.print_header(f"北向资金实时 ({len(valid)} 个时间点)")
        CLIOutput.print_kv("沪股通累计", hgt, " 亿")
        CLIOutput.print_kv("深股通累计", sgt, " 亿")
        CLIOutput.print_kv("北向合计", total, " 亿")
        signal = "净流入" if total > 0 else "净流出"
        CLIOutput.print_kv("方向", signal)
        return 0

    def valuation_calc(self, symbol: str, json_output: bool = False):
        """完整估值分析"""
        data = self.fds.valuation_calc(symbol)
        if not data:
            print(f"错误: 无法对 {symbol} 进行估值分析")
            return 1

        if json_output:
            print(CLIOutput.to_json(data))
            return 0

        CLIOutput.print_header(f"{data.get('name', symbol)} 估值分析")
        CLIOutput.print_kv("当前价", data.get("price"), " 元")
        CLIOutput.print_kv("市值", data.get("mcap_yi"), " 亿")
        CLIOutput.print_kv("PE(TTM)", data.get("pe_ttm"))
        CLIOutput.print_kv("PB", data.get("pb"))
        print()
        CLIOutput.print_kv("当年EPS预测", data.get("eps_cur"))
        CLIOutput.print_kv("次年EPS预测", data.get("eps_next"))
        CLIOutput.print_kv("前向PE", data.get("pe_fwd"), "x")
        CLIOutput.print_kv("EPS增速", data.get("cagr_pct"), "%")
        CLIOutput.print_kv("PEG", data.get("peg"))
        CLIOutput.print_kv("PE消化到30x", data.get("digest_years"), " 年")
        CLIOutput.print_kv("覆盖机构数", data.get("analyst_count"))

        peg = data.get("peg")
        if peg is not None:
            if peg < 1:
                verdict = "便宜 (PEG < 1)"
            elif peg <= 1.5:
                verdict = "合理 (1 ≤ PEG ≤ 1.5)"
            else:
                verdict = "偏贵 (PEG > 1.5)"
            CLIOutput.print_kv("估值判断", verdict)
        return 0

    def consensus_eps_cmd(self, symbol: str, json_output: bool = False):
        """机构一致预期EPS"""
        data = self.fds.consensus_eps(symbol)
        if not data:
            print(f"错误: {symbol} 无机构覆盖或无法获取一致预期")
            return 1

        if json_output:
            print(CLIOutput.to_json(data))
            return 0

        CLIOutput.print_header(f"{symbol} 机构一致预期 EPS")
        headers = ["年度", "机构数", "最小值", "均值", "最大值"]
        rows = [
            [d["year"], d["count"], d.get("min"), d.get("mean", d.get("eps")), d.get("max")]
            for d in data
        ]
        CLIOutput.print_table(headers, rows, precision=4)
        return 0

    # ========== 新闻搜索命令 ==========

    def search(self, query: str, data_type: str = 'news', days: int = 7, json_output: bool = False):
        """搜索新闻/研报/公告"""
        if data_type == 'news':
            data = self.fds.search_news(query, days=days)
        elif data_type == 'report':
            data = self.fds.search_report(query)
        elif data_type == 'announcement':
            data = self.fds.search_announcement(query, days=days)
        else:
            data = self.fds.search(query, data_type=data_type)

        if not data:
            print(f"未找到与 '{query}' 相关的{data_type}")
            return 1

        if json_output:
            print(CLIOutput.to_json(data))
            return 0

        type_names = {'news': '新闻', 'report': '研报', 'announcement': '公告'}
        CLIOutput.print_header(f"搜索结果: {query} ({type_names.get(data_type, data_type)})")

        for i, item in enumerate(data[:10], 1):
            title = item.get('title', item.get('name', '无标题'))
            date = item.get('publish_date', item.get('pub_date', ''))
            source = item.get('source', '')
            print(f"\n  {i}. {title}")
            if date:
                print(f"     日期: {date}")
            if source:
                print(f"     来源: {source}")

        if len(data) > 10:
            print(f"\n  ... 共 {len(data)} 条结果")
        return 0

    # ========== 指数命令 ==========

    def index_quotes(self, json_output: bool = False):
        """获取大盘指数"""
        data = self.fds.index_quotes()
        if not data:
            print("错误: 无法获取指数数据")
            return 1

        if json_output:
            print(CLIOutput.to_json(data))
            return 0

        CLIOutput.print_header("大盘指数")
        # 数据可能是 {'data': {'items': [...]}} 或 {'items': [...]} 或 list
        if isinstance(data, dict):
            inner = data.get('data', data)
            items = inner.get('items', []) if isinstance(inner, dict) else []
        else:
            items = data if isinstance(data, list) else []

        headers = ["代码", "名称", "现价", "涨跌幅%"]
        rows = []
        for item in items:
            rows.append([
                item.get('code', item.get('symbol', '')),
                item.get('name', ''),
                item.get('current', item.get('close', 0)),
                item.get('percent', 0)
            ])
        CLIOutput.print_table(headers, rows)
        return 0

    # ========== 宏观数据命令 ==========

    def macro(self, indicator: str, json_output: bool = False):
        """获取宏观数据"""
        methods = {
            'cpi': self.fds.cn_cpi,
            'ppi': self.fds.cn_ppi,
            'pmi': self.fds.cn_pmi,
            'gdp': self.fds.cn_gdp,
            'm2': self.fds.cn_m,
            'shibor': self.fds.shibor,
        }

        if indicator not in methods:
            print(f"错误: 不支持的宏观指标 '{indicator}'")
            print(f"支持的指标: {', '.join(methods.keys())}")
            return 1

        data = methods[indicator]()

        if data is None or (isinstance(data, list) and not data) or (
            hasattr(data, 'empty') and data.empty
        ):
            print(f"错误: 无法获取 {indicator} 数据")
            return 1

        if json_output:
            if hasattr(data, 'to_dict'):
                print(json.dumps(data.to_dict(orient='records'), ensure_ascii=False, indent=2))
            else:
                print(CLIOutput.to_json(data))
            return 0

        indicator_names = {
            'cpi': 'CPI 居民消费价格指数',
            'ppi': 'PPI 工业生产者出厂价格指数',
            'pmi': 'PMI 采购经理指数',
            'gdp': 'GDP 国内生产总值',
            'm2': 'M2 货币供应量',
            'shibor': 'SHIBOR 上海银行间同业拆放利率',
        }

        CLIOutput.print_header(indicator_names.get(indicator, indicator))
        if isinstance(data, list) and data:
            show = data[:10]
            keys = list(show[0].keys())
            CLIOutput.print_table(keys, [[r.get(k) for k in keys] for r in show])
        elif hasattr(data, 'head'):
            print(data.head(10).to_string(index=False))
        return 0

    # ========== 系统命令 ==========

    def status(self, json_output: bool = False):
        """获取系统状态"""
        data = self.fds.get_status()

        if json_output:
            print(CLIOutput.to_json(data))
            return 0

        CLIOutput.print_header("系统状态")

        cache_stats = data.get('cache', {})
        if isinstance(cache_stats, dict):
            print(f"  缓存条目: {cache_stats.get('size', cache_stats.get('count', 0))}")
        else:
            print(f"  缓存状态: {cache_stats}")

        providers = data.get('providers', {})
        print(f"\n  已注册数据源 ({len(providers)} 个):")
        for name, info in providers.items():
            # info 可能是 bool (is_available) 或 dict
            if isinstance(info, bool):
                status = "✓" if info else "✗"
                print(f"    {status} {name}")
            elif isinstance(info, dict):
                status = "✓" if info.get('available') else "✗"
                priority = info.get('priority', 0)
                print(f"    {status} {name} (优先级: {priority})")
        return 0

    def health(self, json_output: bool = False):
        """健康检查"""
        print("正在执行健康检查...")
        data = self.fds.health_check()

        if json_output:
            print(CLIOutput.to_json(data))
            return 0

        CLIOutput.print_header("健康检查结果")
        all_healthy = True
        for name, healthy in data.items():
            status = "✓ 正常" if healthy else "✗ 异常"
            print(f"  {name}: {status}")
            if not healthy:
                all_healthy = False

        print(f"\n  总体状态: {'✓ 健康' if all_healthy else '✗ 存在问题'}")
        return 0 if all_healthy else 1

    def clear_cache(self):
        """清空缓存"""
        self.fds.clear_cache()
        print("缓存已清空")
        return 0

    def name_to_code(self, name: str, json_output: bool = False, market: Optional[str] = None):
        """名称 → 代码（腾讯 smartbox + A 股 Tushare 兜底）"""
        code = self.fds.name_to_code(name, market=market)
        if not code:
            print(f"错误: 无法将「{name}」解析为证券代码")
            return 1
        if json_output:
            row = {"name": name, "code": code}
            if market:
                row["market"] = market
            print(json.dumps(row, ensure_ascii=False))
            return 0
        print(code)
        return 0

    def code_to_name(self, code: str, json_output: bool = False):
        """代码 → 名称（腾讯 smartbox + A 股 Tushare 兜底）"""
        nm = self.fds.code_to_name(code)
        if not nm:
            print(f"错误: 无法解析代码「{code}」对应的证券简称")
            return 1
        if json_output:
            print(json.dumps({"code": code, "name": nm}, ensure_ascii=False))
            return 0
        print(nm)
        return 0


def create_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        prog='teakfds',
        description='FinanceDataSource CLI - 统一金融数据源命令行工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  fds quote SH600519              # 获取茅台实时行情
  fds valuation SZ000858          # 获取五粮液估值数据
  fds pe-percentile 600519        # 获取茅台PE历史分位
  fds ps-percentile SH600519      # PS-TTM 历史分位
  fds dyr-percentile 600519       # 股息率历史分位
  fds valuation-percentiles SH600519  # 一次输出 PE/PB/PS/股息率 分位
  fds kline SH600519 --period week --count 20  # 获取周K线
  fds search "白酒行业" --type report          # 搜索研报
  fds money-flow 600519 --days 10             # 查询资金流向
  fds north-flow --days 5                      # 北向资金
  fds name-to-code "中国移动"                 # 同名 A+H 时默认首条（多为 A 股）
  fds name-to-code "中国移动" --market hk      # 指定港股代码
  fds code-to-name SH600519                    # 代码→名称

数据类型:
  行情: quote, batch-quote, depth, kline
  代码: name-to-code, code-to-name
  估值: valuation, pe-percentile, pb-percentile, ps-percentile, dyr-percentile, valuation-percentiles, dividend
  估值V2: valuation-calc, consensus-eps
  财务: income, balance, cashflow, indicator
  资金: money-flow, north-flow, north-realtime
  信号: hot-stocks, concept-blocks, dragon-tiger-market, industry-compare
  搜索: search
  指数: index-quotes
  宏观: macro (cpi/ppi/pmi/gdp/m2/shibor)
  系统: status, health, clear-cache
        """
    )

    from teakfds import __version__
    parser.add_argument('-v', '--version', action='version', version=f'%(prog)s {__version__}')

    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # 辅助函数：为每个子解析器添加 json 标志
    def add_json_flag(p):
        p.add_argument('-j', '--json', action='store_true', help='以JSON格式输出')
        return p

    # ========== 行情命令 ==========

    # quote
    p_quote = subparsers.add_parser('quote', help='获取实时行情')
    p_quote.add_argument('symbol', help='股票代码 (如 SH600519)')
    add_json_flag(p_quote)

    # batch-quote
    p_batch = subparsers.add_parser('batch-quote', help='批量获取行情')
    p_batch.add_argument('symbols', nargs='+', help='股票代码列表')
    add_json_flag(p_batch)

    # depth
    p_depth = subparsers.add_parser('depth', help='获取盘口数据')
    p_depth.add_argument('symbol', help='股票代码')
    add_json_flag(p_depth)

    # kline
    p_kline = subparsers.add_parser('kline', help='获取K线数据')
    p_kline.add_argument('symbol', help='股票代码')
    p_kline.add_argument('--period', choices=['day', 'week', 'month'], default='day', help='K线周期')
    p_kline.add_argument('--count', type=int, default=30, help='数据条数')
    add_json_flag(p_kline)

    # name-to-code / code-to-name
    p_ntc = subparsers.add_parser('name-to-code', help='证券名称/关键词 → 代码（腾讯 smartbox，失败则 A 股 Tushare）')
    p_ntc.add_argument('name', help='证券名称或关键词')
    p_ntc.add_argument(
        '-m',
        '--market',
        choices=['a_share', 'hk', 'us'],
        default=None,
        help='同名多市场时选用：a_share=A股，hk=港股，us=美股；省略则取 smartbox 返回的第一条 GP/GP-A',
    )
    add_json_flag(p_ntc)
    p_ctn = subparsers.add_parser('code-to-name', help='证券代码 → 简称（腾讯 smartbox，失败则仅 A 股 Tushare）')
    p_ctn.add_argument('symbol', help='股票代码')
    add_json_flag(p_ctn)

    # ========== 估值命令 ==========

    # valuation
    p_val = subparsers.add_parser('valuation', help='获取估值数据')
    p_val.add_argument('symbol', help='股票代码')
    add_json_flag(p_val)

    # pe-percentile
    p_pe = subparsers.add_parser('pe-percentile', help='获取PE历史分位')
    p_pe.add_argument('symbol', help='股票代码')
    p_pe.add_argument('--years', type=int, default=10, help='历史年数')
    add_json_flag(p_pe)

    # pb-percentile
    p_pb = subparsers.add_parser('pb-percentile', help='获取PB历史分位')
    p_pb.add_argument('symbol', help='股票代码')
    p_pb.add_argument('--years', type=int, default=10, help='历史年数')
    add_json_flag(p_pb)

    # ps-percentile / dyr-percentile / valuation-percentiles
    p_ps = subparsers.add_parser('ps-percentile', help='获取PS-TTM历史分位（理杏仁）')
    p_ps.add_argument('symbol', help='股票代码')
    p_ps.add_argument('--years', type=int, default=10, help='历史年数（5 或 10）')
    add_json_flag(p_ps)
    p_dyr = subparsers.add_parser('dyr-percentile', help='获取股息率历史分位（理杏仁）')
    p_dyr.add_argument('symbol', help='股票代码')
    p_dyr.add_argument('--years', type=int, default=10, help='历史年数（5 或 10）')
    add_json_flag(p_dyr)
    p_vp = subparsers.add_parser(
        'valuation-percentiles',
        help='一次输出 PE/PB/PS-TTM/股息率 历史分位（理杏仁单次请求）',
    )
    p_vp.add_argument('symbol', help='股票代码')
    p_vp.add_argument('--years', type=int, default=10, help='历史年数（5 或 10）')
    add_json_flag(p_vp)

    # dividend
    p_div = subparsers.add_parser('dividend', help='获取分红数据')
    p_div.add_argument('symbol', help='股票代码')
    add_json_flag(p_div)

    # ========== 财务命令 ==========

    # income
    p_income = subparsers.add_parser('income', help='获取利润表')
    p_income.add_argument('symbol', help='股票代码')
    add_json_flag(p_income)

    # balance
    p_balance = subparsers.add_parser('balance', help='获取资产负债表')
    p_balance.add_argument('symbol', help='股票代码')
    add_json_flag(p_balance)

    # cashflow
    p_cashflow = subparsers.add_parser('cashflow', help='获取现金流量表')
    p_cashflow.add_argument('symbol', help='股票代码')
    add_json_flag(p_cashflow)

    # indicator
    p_ind = subparsers.add_parser('indicator', help='获取财务指标')
    p_ind.add_argument('symbol', help='股票代码')
    add_json_flag(p_ind)

    # ========== 资金流向命令 ==========

    # money-flow
    p_mf = subparsers.add_parser('money-flow', help='获取个股资金流向')
    p_mf.add_argument('symbol', help='股票代码')
    p_mf.add_argument('--days', type=int, default=5, help='查询天数')
    add_json_flag(p_mf)

    # north-flow
    p_nf = subparsers.add_parser('north-flow', help='获取北向资金')
    p_nf.add_argument('--days', type=int, default=10, help='查询天数')
    add_json_flag(p_nf)

    # ========== 补充数据源命令 (V2) ==========

    # hot-stocks
    p_hot = subparsers.add_parser('hot-stocks', help='当日强势股 + 题材归因')
    p_hot.add_argument('--date', default=None, help='日期 YYYY-MM-DD（默认今天）')
    add_json_flag(p_hot)

    # concept-blocks
    p_cb = subparsers.add_parser('concept-blocks', help='个股概念/行业/地域板块归属')
    p_cb.add_argument('symbol', help='股票代码')
    add_json_flag(p_cb)

    # dragon-tiger-market
    p_dtm = subparsers.add_parser('dragon-tiger-market', help='全市场龙虎榜')
    p_dtm.add_argument('--date', default=None, help='日期 YYYY-MM-DD（默认今天）')
    p_dtm.add_argument('--min-net-buy', type=float, default=None, help='净买入下限（万元）')
    add_json_flag(p_dtm)

    # industry-compare
    p_ic = subparsers.add_parser('industry-compare', help='行业涨跌排名')
    p_ic.add_argument('--top', type=int, default=20, help='显示条数')
    add_json_flag(p_ic)

    # north-realtime
    p_nr = subparsers.add_parser('north-realtime', help='北向资金实时分钟流向')
    add_json_flag(p_nr)

    # valuation-calc
    p_vc = subparsers.add_parser('valuation-calc', help='完整估值分析（前向PE/PEG/消化时间）')
    p_vc.add_argument('symbol', help='股票代码')
    add_json_flag(p_vc)

    # consensus-eps
    p_ce = subparsers.add_parser('consensus-eps', help='机构一致预期EPS')
    p_ce.add_argument('symbol', help='股票代码')
    add_json_flag(p_ce)

    # ========== 搜索命令 ==========

    # search
    p_search = subparsers.add_parser('search', help='搜索新闻/研报/公告')
    p_search.add_argument('query', help='搜索关键词')
    p_search.add_argument('--type', choices=['news', 'report', 'announcement'], default='news', help='数据类型')
    p_search.add_argument('--days', type=int, default=7, help='查询天数')
    add_json_flag(p_search)

    # ========== 指数命令 ==========

    # index-quotes
    p_idx = subparsers.add_parser('index-quotes', help='获取大盘指数')
    add_json_flag(p_idx)

    # ========== 宏观命令 ==========

    # macro
    p_macro = subparsers.add_parser('macro', help='获取宏观数据')
    p_macro.add_argument('indicator', choices=['cpi', 'ppi', 'pmi', 'gdp', 'm2', 'shibor'], help='宏观指标')
    add_json_flag(p_macro)

    # ========== 系统命令 ==========

    # status
    p_status = subparsers.add_parser('status', help='获取系统状态')
    add_json_flag(p_status)

    # health
    p_health = subparsers.add_parser('health', help='执行健康检查')
    add_json_flag(p_health)

    # clear-cache
    subparsers.add_parser('clear-cache', help='清空缓存')

    return parser


def main():
    """主入口"""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    cmds = FDSCommands()
    json_output = getattr(args, 'json', False)

    # 调度命令
    command_map = {
        'quote': lambda: cmds.quote(args.symbol, json_output),
        'batch-quote': lambda: cmds.batch_quote(args.symbols, json_output),
        'depth': lambda: cmds.depth(args.symbol, json_output),
        'kline': lambda: cmds.kline(args.symbol, args.period, args.count, json_output),

        'name-to-code': lambda: cmds.name_to_code(
            args.name, json_output, getattr(args, 'market', None)
        ),
        'code-to-name': lambda: cmds.code_to_name(args.symbol, json_output),

        'valuation': lambda: cmds.valuation(args.symbol, json_output),
        'pe-percentile': lambda: cmds.pe_percentile(args.symbol, args.years, json_output),
        'pb-percentile': lambda: cmds.pb_percentile(args.symbol, args.years, json_output),
        'ps-percentile': lambda: cmds.ps_percentile(args.symbol, args.years, json_output),
        'dyr-percentile': lambda: cmds.dyr_percentile(args.symbol, args.years, json_output),
        'valuation-percentiles': lambda: cmds.valuation_percentiles_cmd(
            args.symbol, args.years, json_output
        ),
        'dividend': lambda: cmds.dividend(args.symbol, json_output),

        'income': lambda: cmds.income(args.symbol, json_output),
        'balance': lambda: cmds.balance(args.symbol, json_output),
        'cashflow': lambda: cmds.cashflow(args.symbol, json_output),
        'indicator': lambda: cmds.indicator(args.symbol, json_output),

        'money-flow': lambda: cmds.money_flow(args.symbol, args.days, json_output),
        'north-flow': lambda: cmds.north_flow(args.days, json_output),

        'hot-stocks': lambda: cmds.hot_stocks(getattr(args, 'date', None), json_output),
        'concept-blocks': lambda: cmds.concept_blocks(args.symbol, json_output),
        'dragon-tiger-market': lambda: cmds.dragon_tiger_market(
            getattr(args, 'date', None), getattr(args, 'min_net_buy', None), json_output
        ),
        'industry-compare': lambda: cmds.industry_compare(getattr(args, 'top', 20), json_output),
        'north-realtime': lambda: cmds.north_realtime(json_output),
        'valuation-calc': lambda: cmds.valuation_calc(args.symbol, json_output),
        'consensus-eps': lambda: cmds.consensus_eps_cmd(args.symbol, json_output),

        'search': lambda: cmds.search(args.query, args.type, args.days, json_output),

        'index-quotes': lambda: cmds.index_quotes(json_output),

        'macro': lambda: cmds.macro(args.indicator, json_output),

        'status': lambda: cmds.status(json_output),
        'health': lambda: cmds.health(json_output),
        'clear-cache': lambda: cmds.clear_cache(),
    }

    if args.command in command_map:
        return command_map[args.command]()
    else:
        print(f"未知命令: {args.command}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
