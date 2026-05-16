---
name: teak-fds
description: >-
  Teak-FDS（teakfds）统一金融数据源：A/H/美股行情、K线、估值与分位（理杏仁）、财务/宏观（Tushare HTTP）、公告研报、妙想搜索、北向等。当用户需要股票/指数金融数据时使用。必须经 TeakFDS 或 CLI 调用，禁止直接 import tushare 或 akshare。
---

# Teak-FDS

面向 Agent 的**唯一入口**：`TeakFDS`（`FinanceDataSource`）或 `teakfds` / `python -m teakfds`。

## 何时使用

下列场景调用本技能；**完整注意项**见 [facade.md](references/facade.md)。**CLI** 见 [cli.md](references/cli.md)。

**与 AkShare / Tushare 全库的关系**：[api-scope.md](references/api-scope.md) — 门面为 Agent 精选能力 + `tushare()` 逃生舱，非 AkShare 上千函数的一一封装。

### 行情

| 方法 | 说明 |
|------|------|
| `quote(symbol)` | 实时行情；返回 `QuoteData` |
| `batch_quote(symbols)` | 批量实时行情 |
| `quote_ext(symbol)` | 含 PE/PB/换手/市值 |
| `depth(symbol)` | 五档盘口 |
| `intraday(symbol)` | 当日分时 |
| `minute_kline(symbol)` | 雪球分钟 K（需 cookie） |
| `pankou(symbol)` | 雪球盘口 JSON |
| `tick_data(symbol, count)` | 当日逐笔（需 mootdx） |
| `tick_data_history(symbol, date, count)` | 历史逐笔 |

### K 线

| 方法 | 说明 |
|------|------|
| `kline(symbol, period, count, ...)` | 日/周/月 K；`list[KlineData]` |
| `pro_bar(symbol, adj, ...)` | Tushare 复权 K 线 |
| `stk_mins(symbol, freq, ...)` | 分钟 K（Tushare 权限） |

### 估值

| 方法 | 说明 |
|------|------|
| `valuation(symbol)` | 当前 PE/PB/市值；理杏仁→Tushare 降级 |
| `valuation_calc(symbol)` | 前向 PE、PEG、消化年数 |
| `valuation_percentiles(symbol, years)` | PE/PB/PS/股息率分位 bundle |
| `pe_percentile` / `pb_percentile` / `ps_percentile` / `dyr_percentile` | 单指标历史分位 |
| `price_metric_percentile(symbol, metric, years)` | 指定指标分位 |
| `valuation_history(symbol, years)` | 历史估值序列 |
| `dividend(symbol)` | 分红送转 |
| `consensus_eps(symbol)` | 机构一致预期 EPS |
| `refresh_undervalued_pool(...)` | 理杏仁低估池筛选（OpenClaw） |

### 财务

| 方法 | 说明 |
|------|------|
| `income` / `balance_sheet` / `cash_flow` | 三表（统一模型） |
| `financial_indicator` | ROE、毛利率等 |
| `income_df` / `balance_sheet_df` / `cash_flow_df` | 三表原始 `list[dict]` |
| `finance_snapshot` / `f10` / `xdxr` | 快照、F10、除权除息 |
| `forecast` / `express` | 业绩预告 / 快报 |

### 研报 / 评级

| 方法 | 说明 |
|------|------|
| `report_list` | 研报/公告型列表 |
| `report_forecast` | 盈利预测按年 |
| `report_rating` | 机构评级（东财研报→巨潮） |
| `institution_recommend` / `institution_participation` | 机构推荐/参与度 |
| `eastmoney_reports` | 东财研报+PDF |
| `iwencai(question)` | 问财 NL 选股 |

### 公告

| 方法 | 说明 |
|------|------|
| `announcement_list` | 个股公告列表 |
| `announcement_pdf_url` / `announcement_full_text` | PDF 链接 / 全文 |
| `latest_announcements` | 全市场最新公告 |
| `company_events` | 公司动态 |

### 搜索

| 方法 | 说明 |
|------|------|
| `search(query, data_type)` | 妙想搜索；无 `limit` 参数 |
| `search_news` / `search_report` / `search_announcement` | 分类搜索 |

### 资金 / 北向 / 龙虎榜

| 方法 | 说明 |
|------|------|
| `money_flow` / `capital_flow` / `fund_flow_baidu` | 个股资金流 |
| `north_money_flow` / `hsgt_top10` / `north_money_realtime` | 北向历史/十大/实时 |
| `top_list` / `limit_up_down` | 龙虎榜个股 / 涨跌停 |
| `daily_dragon_tiger` | 全市场龙虎榜 |

### 市场信号 / 板块

| 方法 | 说明 |
|------|------|
| `hot_stocks` | 强势股+题材归因 |
| `concept_blocks` | 概念/行业/地域板块 |
| `industry_comparison` | 行业涨跌排名 |
| `market_breadth` | 市场广度（涨跌家数） |

### 指数 / 宏观

| 方法 | 说明 |
|------|------|
| `index_quotes` / `index_list` / `index_kline` | 指数行情与 K 线 |
| `cn_cpi` / `cn_ppi` / `cn_pmi` / `cn_gdp` / `cn_m` / `shibor` | 宏观序列 |

### 雪球

| 方法 | 说明 |
|------|------|
| `cube_rebalancing` / `cube_quote` / `cube_nav` | 组合调仓/报价/净值 |
| `watchlist_stocks` | 自选股（需 cookie） |

### F10 深度

| 方法 | 说明 |
|------|------|
| `insider_trading` | 高管增减持 |
| `top_holders` / `top_float_holders` | 十大股东 / 流通股东 |
| `shareholder_count` | 股东人数 |
| `managers` / `main_business` | 高管 / 主营构成 |
| `share_unlock` / `survey_activities` | 解禁 / 调研 |

### 基础 / 系统 / Tushare 逃生舱

| 方法 | 说明 |
|------|------|
| `stock_basic` | 股票列表 |
| `name_to_code` / `code_to_name` | 名称↔代码 |
| `trade_cal` | 交易日历 |
| `tushare(api, **kwargs)` | 任意 Tushare Pro API |
| `get_provider` / `get_status` / `health_check` / `clear_cache` | Provider 与系统 |

## 快速开始

```python
from teakfds import TeakFDS

fds = TeakFDS()
q = fds.quote("SH600519")
bars = fds.kline("SH600519", count=5)
rows = fds.tushare("daily", ts_code="600519.SH", start_date="20250501", end_date="20250510")
```

```bash
cd ~/.openclaw/skills/teak-fds && pip install -e .
teakfds quote SH600519 --json
```

## 必读约定

1. 符号：门面 `SH600519`；`tushare` 用 `600519.SH`。
2. dataclass 用属性；`list[dict]` 用键。
3. 失败多为 `None`。
4. 禁止 `import tushare` / `import akshare`。

详见 [data-types.md](references/data-types.md)。

## 参考文档

| 文档 | 内容 |
|------|------|
| [facade.md](references/facade.md) | 完整 API（含说明列） |
| [cli.md](references/cli.md) | CLI 全集 |
| [api-scope.md](references/api-scope.md) | 与 AkShare/Tushare 全库关系 |
| [data-types.md](references/data-types.md) | 返回类型 |
| [install.md](references/install.md) | 安装 |
| [agent-validation.md](references/agent-validation.md) | 验证 |
| [routing.md](references/routing.md) | 路由 |
| [config.md](references/config.md) | 凭证 |
| [internal-apis.md](references/internal-apis.md) | 内部 HTTP |
