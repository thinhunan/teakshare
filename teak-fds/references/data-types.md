# 返回数据类型（实测约定）

本文档基于 `tests/test_return_shapes.py` 与联网抽样（2026-05-16）。**Agent 必须按此访问字段**，避免把 dataclass 当 dict 用。

## 总则

| 规则 | 说明 |
|------|------|
| 失败 | 无数据时多为 `None`，不是空列表 |
| dataclass | 用 **属性**：`q.current`；序列化用 `q.to_dict()` |
| list[dict] | 用 **键**：`row["ts_code"]` |
| 符号 | 门面输入推荐 `SH600519`；Tushare 参数用 `600519.SH` |
| CLI `--json` | stdout 为 JSON（dataclass 已 `to_dict()`）；stderr 为日志 |

## 符号格式

| 场景 | 格式 | 示例 |
|------|------|------|
| `TeakFDS.quote/kline/valuation` 等 | 前缀码 | `SH600519`, `SZ000001`, `HK00700` |
| `fds.tushare(..., ts_code=)` | 后缀码 | `600519.SH` |
| 自然语言 | 自动解析 | `贵州茅台` → 内部再路由 |

---

## 实时行情 `quote(symbol)`

- **返回**：`QuoteData | None`
- **访问**：`q.current`, `q.percent`, `q.name`, `q.source`（常见 `tencent`）
- **勿用**：`q["current"]`

主要字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| symbol | str | 如 `SH600519` |
| name | str | 证券简称 |
| current | float | 现价 |
| open/high/low/close | float | 开高低 / 昨收 |
| volume | int | 成交量（股） |
| amount | float | 成交额（元） |
| percent | float | 涨跌幅 % |
| pe_ttm, pb | float? | 扩展估值（腾讯源常有） |
| total_market_cap | float? | 总市值（**亿**） |
| source | str | 实际数据源 |

`batch_quote(symbols)` → `list[QuoteData]`（仅含成功项，顺序与输入一致）。

---

## K 线 `kline(symbol, period='day', count=30, ...)`

- **返回**：`list[KlineData] | None`
- **访问**：`bars[0].close`, `bars[0].date`（**不是** `bars[0]['close']`）

| 字段 | 类型 | 说明 |
|------|------|------|
| date | str | `YYYY-MM-DD` |
| open/high/low/close | float | OHLC |
| volume | int | 成交量 |
| amount | float | 成交额 |
| adjust_factor | float? | Qlib 源常有 |
| turnover, pct_change | float? | 可选 |

**重要**：

- A 股日线路由含 **Qlib** 时，价格为 **前复权**（与行情 `current` 量纲可能差很多）；`count > 500` 时更倾向 Qlib。
- 需未复权或指定复权：传 `adj='qfq'|'hfq'|'none'`（日线，见 facade 注释）或控制 `count` 走网络源。

---

## 估值 `valuation(symbol)`

- **返回**：`ValuationData | None`
- **路由**：理杏仁 → Tushare → 雪球；理杏仁不可用时常见 `source='tushare'`

| 字段 | 类型 | 说明 |
|------|------|------|
| symbol, name | str | |
| pe_ttm, pe_lyr, pb, ps_ttm | float? | |
| dividend_yield | float? | 股息率 |
| market_cap | float? | 总市值（**亿**） |
| source | str | `lixinger` / `tushare` / `xueqiu` |

`valuation_percentiles(symbol, years=10)` → `dict | None`，键含 `pe_ttm`/`pb`/`ps_ttm`/`dyr`（各为分位结构 dict），**需理杏仁可用**。

`valuation_calc(symbol)` → `dict | None`，键示例：

`name`, `price`, `mcap_yi`, `pe_ttm`, `pb`, `eps_cur`, `eps_next`, `pe_fwd`, `cagr_pct`, `peg`, `digest_years`, `analyst_count`

---

## Tushare 逃生舱 `tushare(api, **kwargs)`

- **返回**：`list[dict] | None`（**无 DataFrame**）
- **调用**：`fds.tushare('daily', ts_code='600519.SH', ...)` — `tushare` 是**方法**，不是属性
- **日期**：`trade_date` 等多为 `YYYYMMDD` 字符串

示例：

```python
rows = fds.tushare("daily", ts_code="600519.SH", start_date="20250501", end_date="20250510",
                   fields="ts_code,trade_date,close")
# rows[0]["close"]
```

---

## 研报 / 盈利预测

| 方法 | 返回 | 元素类型 |
|------|------|----------|
| `report_forecast(symbol)` | `list[dict] \| None` | `year`, `eps`, `count` |
| `consensus_eps(symbol)` | `list[dict] \| None` | `year`, `count`, `min`, `mean`, `max`, `industry_avg` |
| `report_list(...)` | `list[dict] \| None` | 公告型字段（常走巨潮） |

---

## 公告 `announcement_list(symbol, ...)`

- **返回**：`list[dict] | None`（cninfo 路由）
- **键**：`title`, `date`, `category`, `url`（相对路径，PDF 需拼接巨潮静态域）, `sec_code`, `source`（`cninfo`）

`announcement_pdf_url(adjunct_url)` → 完整 PDF URL 字符串。

---

## 搜索 `search(query, data_type='news')`

- **返回**：`list[dict] | None`
- **无** `limit` 参数；类型由 `data_type` 控制：`news` / `report` / `announcement` / `all`

| 键 | 说明 |
|----|------|
| title, content, date | 标题/摘要/时间 |
| type | 如 `news` |
| url, entity, rating | 可能为空字符串 |

---

## 行业对比 `industry_comparison(top_n=20)`

- **返回**：`dict | None`

```python
{
  "top": [{"rank", "name", "code", "change_pct", "turnover_yi", ...}, ...],
  "bottom": [...],
  "total": int
}
```

---

## 盘口 / 分时

| 方法 | 返回 |
|------|------|
| `depth(symbol)` | `DepthData \| None`（五档，`.bid1` / `.get_bids_list()`） |
| `intraday(symbol)` | `list[IntradayData] \| None` |
| `minute_kline` / `pankou` | `dict`（雪球原始 JSON） |

---

## 财务三表（Tushare 封装）

`income` / `balance` / `cashflow` / `indicator` 等 → 多为 `list[dict] | None`（经 Tushare HTTP），字段名与 Tushare 官方一致。

---

## 常见错误对照

| 错误写法 | 正确 |
|----------|------|
| `fds.tushare.daily(...)` | `fds.tushare('daily', ...)` |
| `kline[0]['close']` | `kline[0].close` |
| `quote['current']` | `quote.current` |
| `fds.kline('600519.SH')` | `fds.kline('SH600519')` |
| `search(q, limit=5)` | 无 limit；用返回列表切片 |
| 腾讯字段 43 当 PB | 43 为振幅%；PB 在扩展字段 `pb`（见 quote） |
