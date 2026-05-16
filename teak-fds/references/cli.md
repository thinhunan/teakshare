# CLI 完整参考

入口：`teakfds` 或 `python -m teakfds`（先 `pip install -e .`，见 [install.md](install.md)）。

全局选项：`-j` / `--json`（stdout 输出 JSON）；`-h` 查看帮助。

**说明**：CLI 覆盖投研高频命令；其余门面方法用 Python（见文末「仅 Python」）。

---

## 行情

```bash
teakfds quote SH600519 --json
teakfds batch-quote SH600519 SZ000001 --json
teakfds depth SH600519 --json
teakfds kline SH600519 --period day --count 30 --json
teakfds kline SH600519 --period week --count 20 --json
```

| 命令 | 参数 | 对应门面 |
|------|------|----------|
| `quote` | `symbol` | `quote()` |
| `batch-quote` | 多个 `symbol` | `batch_quote()` |
| `depth` | `symbol` | `depth()` |
| `kline` | `symbol` `--period` `--count` | `kline()` |

---

## 代码转换

```bash
teakfds name-to-code "贵州茅台" --json
teakfds name-to-code "中国移动" --market hk --json
teakfds code-to-name SH600519 --json
```

---

## 估值

```bash
teakfds valuation SH600519 --json
teakfds pe-percentile SH600519 --years 10 --json
teakfds pb-percentile SH600519 --years 10 --json
teakfds ps-percentile SH600519 --json
teakfds dyr-percentile SH600519 --json
teakfds valuation-percentiles SH600519 --years 10 --json
teakfds dividend SH600519 --json
teakfds valuation-calc SH600519 --json
teakfds consensus-eps SH600519 --json
```

---

## 财务

```bash
teakfds income SH600519 --json
teakfds balance SH600519 --json
teakfds cashflow SH600519 --json
teakfds indicator SH600519 --json
```

---

## 资金 / 北向 / 信号

```bash
teakfds money-flow SH600519 --days 10 --json
teakfds north-flow --days 5 --json
teakfds north-realtime --json
teakfds hot-stocks --date 2026-05-15 --json
teakfds concept-blocks SH600519 --json
teakfds dragon-tiger-market --date 2026-05-15 --json
teakfds industry-compare --top 20 --json
```

| 命令 | 说明 |
|------|------|
| `money-flow` | 个股资金流 `--days` |
| `north-flow` | 北向历史 `--days` |
| `north-realtime` | 北向分钟实时 |
| `hot-stocks` | 强势股题材 `--date` 可选 |
| `concept-blocks` | 概念/行业板块 |
| `dragon-tiger-market` | 全市场龙虎榜 |
| `industry-compare` | 行业涨跌 `--top` |

---

## 搜索 / 指数 / 宏观

```bash
teakfds search "贵州茅台" --type news --json
teakfds search "白酒" --type report --json
teakfds search "600519" --type announcement --days 30 --json
teakfds index-quotes --json
teakfds macro cpi --json
teakfds macro ppi --json
teakfds macro pmi --json
teakfds macro gdp --json
teakfds macro m2 --json
teakfds macro shibor --json
```

`search --type`：`news` | `report` | `announcement` | `all`

---

## 系统

```bash
teakfds status --json
teakfds health --json
teakfds clear-cache
teakfds -h
```

---

## 仅 Python（无 CLI 子命令）

以下请 `from teakfds import TeakFDS` 后调用，完整说明见 [facade.md](facade.md)：

```python
from teakfds import TeakFDS
fds = TeakFDS()

# 行情扩展
fds.quote_ext("SH600519")
fds.intraday("SH600519")
fds.tick_data("SH600519", count=100)

# 研报公告
fds.announcement_list("SH600519")
fds.report_rating("SH600519")
fds.report_forecast("SH600519")
fds.eastmoney_reports("SH600519")

# 信号 / 板块
fds.daily_dragon_tiger()
fds.fund_flow_baidu("SH600519", days=20)

# F10 / 股东
fds.top_holders("SH600519")
fds.share_unlock("SH600519")

# 问财
fds.iwencai("市盈率小于20且ROE大于15%")

# Tushare 任意 API
fds.tushare("moneyflow_hsgt", start_date="20260101", end_date="20260131")
fds.tushare("concept_detail", ts_code="600519.SH")
```

---

## 输出约定

- **`--json`**：stdout 为 JSON（dataclass 已 `to_dict()`）
- **无 `--json`**：人类可读表格
- Provider 加载与错误在 **stderr**

字段含义：[data-types.md](data-types.md)
