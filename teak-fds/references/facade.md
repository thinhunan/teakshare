# Facade API 完整索引

`TeakFDS` = `FinanceDataSource`（`teakfds/finance_data_source.py`）。

- **符号**：门面用 `SH600519`；`tushare(..., ts_code='600519.SH')` 用后缀格式。
- **返回类型**：见 [data-types.md](data-types.md)。
- **能力边界**：见 [api-scope.md](api-scope.md)（为何少于 AkShare/Tushare 全库）。

列说明：**说明** = 功能 + 使用注意。

---

## 行情

| 方法 | 返回类型 | 说明 |
|------|----------|------|
| `quote(symbol)` | `QuoteData \| None` | 实时行情（腾讯等）。用 `.current` 非 `['current']`。 |
| `batch_quote(symbols)` | `list[QuoteData]` | 批量行情；仅含成功项。 |
| `quote_ext(symbol)` | `QuoteData \| None` | 扩展行情：PE/PB/换手/市值等。 |
| `depth(symbol)` | `DepthData \| None` | 五档盘口。 |
| `intraday(symbol)` | `list[IntradayData] \| None` | 当日分时。 |
| `minute_kline(symbol, period='1d')` | `dict \| None` | 雪球分钟 K 线原始 JSON；需雪球 cookie。 |
| `pankou(symbol)` | `dict \| None` | 雪球盘口原始 JSON。 |
| `tick_data(symbol, count=800)` | `list \| None` | 当日逐笔；需 **mootdx** 可选依赖。 |
| `tick_data_history(symbol, date, count=800)` | `list \| None` | 历史逐笔；需 mootdx。 |

---

## K 线

| 方法 | 返回类型 | 说明 |
|------|----------|------|
| `kline(symbol, period='day', count=30, start_date=, end_date=, adj=)` | `list[KlineData] \| None` | 日/周/月 K；`count>500` 倾向 Qlib 前复权，与 `quote.current` 量纲可能不同。 |
| `pro_bar(symbol, start_date, end_date, adj='qfq', freq='D')` | `list[dict] \| None` | Tushare 复权 K 线。 |
| `stk_mins(symbol, start_date, end_date, freq='1min')` | `list[dict] \| None` | 分钟线（Tushare）；需权限与积分。 |

---

## 估值

| 方法 | 返回类型 | 说明 |
|------|----------|------|
| `valuation(symbol)` | `ValuationData \| None` | PE/PB/市值等；理杏仁 → Tushare → 雪球。 |
| `valuation_calc(symbol)` | `dict \| None` | 前向 PE、PEG、PE 消化年数等。 |
| `valuation_history(symbol, years=10)` | `dict \| None` | 历史估值序列；理杏仁。 |
| `valuation_percentiles(symbol, years=10)` | `dict \| None` | PE/PB/PS/股息率四套分位一次取；需理杏仁。 |
| `pe_percentile(symbol, years=10)` | `dict \| None` | PE-TTM 历史分位。 |
| `pb_percentile(symbol, years=10)` | `dict \| None` | PB 历史分位。 |
| `ps_percentile(symbol, years=10)` | `dict \| None` | PS-TTM 历史分位。 |
| `dyr_percentile(symbol, years=10)` | `dict \| None` | 股息率历史分位。 |
| `price_metric_percentile(symbol, metric, years=10)` | `dict \| None` | 单指标分位；`metric` 为 `pe_ttm`/`pb`/`ps_ttm`/`dyr`。 |
| `dividend(symbol)` | `list[dict] \| None` | 分红送转（Tushare）。 |
| `consensus_eps(symbol)` | `list[dict] \| None` | 机构一致预期 EPS 按年。 |
| `refresh_undervalued_pool(...)` | `dict` | 理杏仁低估池筛选并写 JSON；OpenClaw 集成用。 |

---

## 财务三表与快照

| 方法 | 返回类型 | 说明 |
|------|----------|------|
| `income(symbol, period=None)` | `IncomeData \| None` | 利润表（统一模型）。 |
| `balance_sheet(symbol, period=None)` | `BalanceData \| None` | 资产负债表。 |
| `cash_flow(symbol, period=None)` | `CashFlowData \| None` | 现金流量表。 |
| `financial_indicator(symbol, period=None)` | `FinancialIndicator \| None` | ROE/毛利率等。 |
| `income_df(symbol, period=None)` | `list[dict] \| None` | 利润表原始行（Tushare 字段名）。 |
| `balance_sheet_df(symbol, period=None)` | `list[dict] \| None` | 资产负债表原始行。 |
| `cash_flow_df(symbol, period=None)` | `list[dict] \| None` | 现金流原始行。 |
| `finance_snapshot(symbol)` | `dict \| None` | EPS/股本/股东人数等快照；需 mootdx。 |
| `f10(symbol, category=None)` | `dict \| None` | F10 资料分类；需 mootdx。 |
| `xdxr(symbol)` | `list[dict] \| None` | 除权除息。 |
| `forecast(symbol, ...)` | `list[dict] \| None` | 业绩预告（Tushare）。 |
| `express(symbol, ...)` | `list[dict] \| None` | 业绩快报（Tushare）。 |

---

## 研报 / 评级 / 预测

| 方法 | 返回类型 | 说明 |
|------|----------|------|
| `report_list(symbol, start_date, end_date)` | `list[dict] \| None` | 研报/公告型列表（路由 aggregate/巨潮）。 |
| `report_forecast(symbol)` | `list[dict] \| None` | 盈利预测按年：`year`, `eps`, `count`。 |
| `report_rating(symbol)` | `list[dict] \| None` | 机构评级；单股优先东财研报，其次巨潮按日列表。 |
| `institution_recommend(symbol)` | `list[dict] \| None` | 机构推荐（东财）。 |
| `institution_participation(symbol)` | `dict \| None` | 机构参与度（东财）。 |
| `eastmoney_reports(symbol, max_pages=3)` | `list[dict] \| None` | 东财研报列表含 PDF 链接与评级。 |
| `iwencai(question, **kwargs)` | `list[dict] \| None` | 问财 NL 选股；需 Node/pywencai 环境。 |

---

## 公告

| 方法 | 返回类型 | 说明 |
|------|----------|------|
| `announcement_list(symbol, category='', start_date, end_date)` | `list[dict] \| None` | 个股公告；键 `title`,`date`,`url`,`source`。 |
| `announcement_pdf_url(adjunct_url)` | `str \| None` | 巨潮 PDF 完整 URL。 |
| `announcement_full_text(adjunct_url)` | `str \| None` | 公告全文（若已配置 PDF 解析）。 |
| `latest_announcements(date, category='全部')` | `list[dict] \| None` | 全市场最新公告。 |
| `company_events(date)` | `list[dict] \| None` | 公司动态（东财）。 |

---

## 搜索（妙想）

| 方法 | 返回类型 | 说明 |
|------|----------|------|
| `search(query, data_type='news')` | `list[dict] \| None` | 通用搜索；`data_type`: news/report/announcement/all；**无 limit**。 |
| `search_news(query, days=7)` | `list[dict] \| None` | 新闻搜索。 |
| `search_report(query)` | `list[dict] \| None` | 研报搜索。 |
| `search_announcement(query, days=30)` | `list[dict] \| None` | 公告搜索。 |

---

## 资金流向 / 北向 / 龙虎榜

| 方法 | 返回类型 | 说明 |
|------|----------|------|
| `money_flow(symbol, days=30)` | `list[dict] \| None` | 个股资金流向日线。 |
| `capital_flow(symbol)` | `dict \| None` | 分钟级资金（若 Provider 支持）。 |
| `fund_flow_baidu(symbol, days=20)` | `list[dict] \| None` | 百度股市通资金流备选源。 |
| `north_money_flow(start_date, end_date)` | `list[dict] \| None` | 北向资金历史（Tushare）。 |
| `hsgt_top10(trade_date=None)` | `list[dict] \| None` | 沪深港通十大成交股；不传日期取最新。 |
| `north_money_realtime()` | `list[dict] \| None` | 北向实时分钟（同花顺）。 |
| `top_list(trade_date=None)` | `list[dict] \| None` | 龙虎榜个股（Tushare）。 |
| `limit_up_down(trade_date=None)` | `list[dict] \| None` | 涨跌停统计（Tushare）。 |
| `daily_dragon_tiger(trade_date, min_net_buy)` | `dict \| None` | 全市场龙虎榜（东财 datacenter）。 |

---

## 市场信号 / 板块

| 方法 | 返回类型 | 说明 |
|------|----------|------|
| `hot_stocks(trade_date=None)` | `list[dict] \| None` | 强势股 + 题材归因（同花顺）。 |
| `concept_blocks(symbol)` | `dict \| None` | 行业/概念/地域；百度失败走 Tushare `concept_detail`。 |
| `industry_comparison(top_n=20)` | `dict \| None` | 行业涨跌榜 `{top,bottom,total}`；东财 push2 失败走 `moneyflow_ind_ths`。 |
| `market_breadth(trade_date=None)` | `dict \| None` | 市场广度（涨跌家数等）。 |

---

## 指数

| 方法 | 返回类型 | 说明 |
|------|----------|------|
| `index_quotes()` | `dict \| None` | 主要指数实时行情。 |
| `index_list(market=None)` | `list[dict] \| None` | 指数列表。 |
| `index_kline(index_code, start_date, end_date)` | `list[dict] \| None` | 指数 K 线，如 `000001.SH`。 |

---

## 宏观

| 方法 | 返回类型 | 说明 |
|------|----------|------|
| `cn_cpi(month=None)` | `list[dict] \| None` | CPI。 |
| `cn_ppi(month=None)` | `list[dict] \| None` | PPI。 |
| `cn_pmi(month=None)` | `list[dict] \| None` | PMI。 |
| `cn_gdp(quarter=None)` | `list[dict] \| None` | GDP。 |
| `cn_m(month=None)` | `list[dict] \| None` | 货币供应量 M0/M1/M2。 |
| `shibor(date=None)` | `list[dict] \| None` | Shibor 利率。 |

---

## 雪球

| 方法 | 返回类型 | 说明 |
|------|----------|------|
| `cube_rebalancing(cube_symbol, count=20, page=1)` | `dict \| None` | 组合调仓记录。 |
| `cube_quote(symbol)` | `dict \| None` | 组合相关报价。 |
| `cube_nav(cube_symbol, days=90)` | `dict \| None` | 组合净值曲线。 |
| `watchlist_stocks()` | `dict \| None` | 自选股列表；需雪球 cookie。 |

---

## F10 深度（Tushare）

| 方法 | 返回类型 | 说明 |
|------|----------|------|
| `insider_trading(symbol)` | `list[dict] \| None` | 高管增减持。 |
| `top_holders(symbol)` | `list[dict] \| None` | 十大股东。 |
| `top_float_holders(symbol)` | `list[dict] \| None` | 十大流通股东。 |
| `shareholder_count(symbol)` | `list[dict] \| None` | 股东人数变化。 |
| `managers(symbol)` | `list[dict] \| None` | 公司高管。 |
| `main_business(symbol, biz_type='P')` | `list[dict] \| None` | 主营构成；`P` 产品 / `D` 地区。 |
| `share_unlock(symbol)` | `list[dict] \| None` | 限售解禁。 |
| `survey_activities(symbol)` | `list[dict] \| None` | 机构调研活动。 |

---

## 基础信息 / 工具

| 方法 | 返回类型 | 说明 |
|------|----------|------|
| `stock_basic(symbol, name, ...)` | `list[dict] \| None` | 股票列表/查询。 |
| `name_to_code(name, market=None)` | `str \| None` | 名称→代码；`market` 可选 a_share/hk/us。 |
| `code_to_name(code)` | `str \| None` | 代码→简称。 |
| `trade_cal(start_date, end_date, exchange='SSE')` | `list[dict] \| None` | 交易日历。 |
| `tushare(api, **kwargs)` | `list[dict] \| None` | **Tushare Pro 逃生舱**；`api` 为官方接口名，非属性。 |
| `get_provider(name)` | `BaseProvider \| None` | 按名取 Provider（高级）。 |
| `get_status()` | `dict` | Provider/缓存/限流状态。 |
| `health_check()` | `dict` | 各 Provider 可用性。 |
| `clear_cache()` | `None` | 清空内存缓存。 |

---

## 模块级便捷函数

`from teakfds import quote, kline, valuation, valuation_percentiles, name_to_code, code_to_name, search` — 等价于 `get_finance_data_source()` 单方法调用。

---

## 模型

`teakfds/models.py`：`QuoteData`, `KlineData`, `ValuationData`, `DepthData`, `IntradayData` 等，均支持 `.to_dict()`。
