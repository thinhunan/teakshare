# Facade API 索引

`TeakFDS` 与 `FinanceDataSource` 为同一类（`teakfds/finance_data_source.py`）。

**返回类型与字段请以 [data-types.md](data-types.md) 为准**（含 dataclass vs dict、符号格式、常见错误）。

## 行情

| 方法 | 返回类型 |
|------|----------|
| `quote(symbol)` | `QuoteData \| None` |
| `batch_quote(symbols)` | `list[QuoteData]` |
| `quote_ext(symbol)` | `QuoteData \| None`（含扩展估值字段） |
| `depth(symbol)` | `DepthData \| None` |
| `intraday(symbol)` | `list[IntradayData] \| None` |

## K 线

| 方法 | 返回类型 |
|------|----------|
| `kline(symbol, period='day', count=30, start_date=, end_date=, adj=)` | `list[KlineData] \| None` |
| `pro_bar(...)` | `list[dict] \| None`（Tushare 复权 K 线） |

## 估值

| 方法 | 返回类型 |
|------|----------|
| `valuation(symbol)` | `ValuationData \| None` |
| `valuation_percentiles(symbol, years=10)` | `dict \| None` |
| `pe_percentile` / `pb_percentile` / … | `dict \| None` |
| `valuation_calc(symbol)` | `dict \| None` |

## Tushare

| 方法 | 返回类型 |
|------|----------|
| `tushare(api, **kwargs)` | `list[dict] \| None` |
| `income` / `balance` / `cashflow` / `indicator` | `list[dict] \| None` |

## 公告 / 研报 / 搜索

| 方法 | 返回类型 |
|------|----------|
| `announcement_list(...)` | `list[dict] \| None` |
| `report_forecast` / `consensus_eps` | `list[dict] \| None` |
| `search(query, data_type='news')` | `list[dict] \| None` |

## 市场特色

| 方法 | 返回类型 |
|------|----------|
| `industry_comparison(top_n=20)` | `dict \| None` |
| `hot_stocks` / `concept_blocks` / `dragon_tiger_market` | `list[dict]` 或 `dict`（见实现） |
| `money_flow` / `north_flow` | `list[dict] \| None` |

## 工具

| 方法 | 返回类型 |
|------|----------|
| `get_status()` | `dict` |
| `name_to_code` / `code_to_name` | `str \| None` |

## 模型定义

`teakfds/models.py`：`QuoteData`, `KlineData`, `ValuationData` 等均提供 `to_dict()`。
