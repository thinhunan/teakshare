# Agent 功能验证指南

本文档供 **Agent 在接入或升级 teak-fds 后** 按步骤自检：能力是否齐全、返回是否正常、类型是否符合 [data-types.md](data-types.md)。

---

## 1. 能力范围说明（避免误解）

| 对比对象 | teak-fds 承诺 |
|----------|----------------|
| **finance-data-source (FDS)** | **门面 API 1:1 对齐**：`TeakFDS` / `FinanceDataSource` 上列出的公开方法均已迁入（见 [facade.md](facade.md)）。 |
| **AkShare 全库** | **不对齐**。仅覆盖 FDS 原先经 `akshare` 路由的能力，由 `aggregate` Provider + `integrations/*` 内部 HTTP 实现（巨潮/东财/同花顺），**不安装、不 import akshare**。 |
| **Tushare Pro 全 API** | 经 `fds.tushare(api, **kwargs)` 逃生舱调用；需 `~/agents_documents/TUSHARE_TOKEN.txt`。 |

新增能力（相对旧 FDS）：`market_breadth()` 等见 `finance_data_source.py`。

---

## 2. 前置条件

```bash
# 技能已链接且已安装（见 install.md）
ls ~/.openclaw/skills/teak-fds
pip install -e ~/.openclaw/skills/teak-fds

# 推荐凭证（缺则部分接口 skip/降级，不阻塞行情）
# ~/agents_documents/TUSHARE_TOKEN.txt
# ~/agents_documents/MX_APIKEY.txt
# teakfds/providers/lixinger/settings.json + cookie.txt（仅技能内目录，勿指向 finance-data-source）
```

**禁止**依赖 `PYTHONPATH`；应使用 `pip install -e .` 后的全局 `teakfds` 包。

### 全量 API 验证（推荐）

```bash
cd teak-fds
python scripts/verify_all_apis.py --strict
python scripts/verify_all_apis.py --strict --symbol SZ300750,SH600519
python scripts/verify_capabilities.py
```

`--strict` 检查字段语义（如 `motion.amount`、`money_flow.main_net`、`consensus_eps.eps`），避免「有返回但全零 / 缺别名」。

---

## 3. 一键验证（推荐）

在技能根目录执行：

```bash
cd ~/.openclaw/skills/teak-fds

# 离线结构测试
python3 -m pytest tests/ -q -m "not integration"

# 联网能力矩阵（约 15–30 秒）
python3 scripts/verify_capabilities.py

# 快速核心 13 项
python3 scripts/verify_capabilities.py --quick

# JSON 报告（便于 Agent 解析）
python3 scripts/verify_capabilities.py --json > /tmp/teakfds-verify.json
```

### 结果判定

| 状态 | 含义 | Agent 动作 |
|------|------|------------|
| **PASS** | 有数据且类型/字段符合检查器 | 可放心调用 |
| **SKIP** | 标记为 optional，或 None（缺 Token/外部 API 限流） | 查凭证或换时段重试；不视为回归 |
| **FAIL** | 必需项无数据或类型错误 | 查 stderr 日志、`~/.openclaw/logs/dataproxy/dataproxy.log` |

**最近一次全量参考**（2026-05-16）：34 项中 **28 PASS / 0 FAIL / 6 SKIP**（SKIP 多为理杏仁分位、百度板块、东财行业榜瞬时断连）。

---

## 4. 分模块手验清单

测试标的默认 **`SH600519`（贵州茅台）**；Tushare 参数用 **`600519.SH`**。

### 4.1 行情与 K 线（FDS 核心）

```python
from teakfds import TeakFDS
fds = TeakFDS(use_cache=False)

q = fds.quote("SH600519")
assert q and q.current > 0          # QuoteData，属性访问
assert q.source

bars = fds.kline("SH600519", count=5)
assert bars and bars[0].close       # list[KlineData]
```

CLI：

```bash
teakfds quote SH600519 --json | python3 -m json.tool | head
teakfds kline SH600519 --count 5 --json
```

### 4.2 估值（理杏仁 → Tushare 降级）

```python
v = fds.valuation("SH600519")
assert v and v.pe_ttm is not None   # ValuationData

calc = fds.valuation_calc("SH600519")
# dict: pe_ttm, pe_fwd, peg, digest_years ...
```

理杏仁未配置时：`valuation.source` 可能为 `tushare`；`valuation_percentiles` / `pe_percentile` 常为 **None**（SKIP 正常）。

### 4.3 Tushare 逃生舱

```python
rows = fds.tushare("daily", ts_code="600519.SH",
                   start_date="20250501", end_date="20250510",
                   fields="ts_code,trade_date,close")
assert rows and "close" in rows[0]   # list[dict]，非 DataFrame
```

**禁止**：`fds.tushare.daily(...)`、`import tushare`。

### 4.4 公告 / 研报（原 AkShare 区 → aggregate）

```python
ann = fds.announcement_list("SH600519")
assert ann and "title" in ann[0] and ann[0].get("source") == "cninfo"

fc = fds.report_forecast("SH600519")
assert fc and "year" in fc[0] and "eps" in fc[0]

eps = fds.consensus_eps("SH600519")  # 可能 None（同花顺页需 analytics extra）
```

### 4.5 搜索（妙想）

```python
news = fds.search("贵州茅台", data_type="news")
# list[dict]；无 limit 参数
```

需 `MX_APIKEY.txt`；失败返回 **None** 而非 `[]`。

### 4.6 信号与板块（V2）

```python
fds.hot_stocks()                    # list[dict] | None
fds.daily_dragon_tiger()            # dict | None
fds.north_money_realtime()          # list[dict] | None
fds.industry_comparison(top_n=5)    # dict{top,bottom,total} | None（东财 push2 可能断连）
fds.concept_blocks("SH600519")      # dict | None（百度 API 可能 ResultCode≠0）
```

### 4.7 系统

```bash
teakfds status
teakfds health
```

---

## 5. FDS 能力对照表

以下方法在 `teakfds/finance_data_source.py` 中均已实现（与 FDS SKILL 一致）：

| 分类 | 方法 | 返回类型要点 |
|------|------|----------------|
| 行情 | `quote`, `batch_quote`, `quote_ext`, `depth`, `intraday`, `tick_data*` | `QuoteData` / `DepthData` / `list[IntradayData]` |
| K线 | `kline`, `pro_bar`, `stk_mins`, `minute_kline` | `list[KlineData]` 或 `list[dict]` |
| 财务 | `income*`, `balance_sheet*`, `cash_flow*`, `financial_indicator`, `finance_snapshot`, `f10`, `xdxr` | dataclass 或 `list[dict]` |
| 估值 | `valuation`, `valuation_*`, `valuation_calc`, `dividend` | `ValuationData` / `dict` |
| 资金 | `money_flow`, `capital_flow`, `north_money_flow`, `hsgt_top10`, `top_list`, `limit_up_down` | `list[dict]` / `dict` |
| 研报公告 | `report_*`, `announcement_*`, `iwencai`, `institution_*` | `list[dict]` |
| 搜索 | `search`, `search_news/report/announcement` | `list[dict]` |
| 指数宏观 | `index_*`, `cn_cpi/ppi/pmi/gdp/m`, `shibor` | `list[dict]` |
| 雪球 | `cube_*`, `watchlist_stocks`, `pankou` | `dict` |
| F10深度 | `insider_trading`, `top_holders`, `share_unlock`, … | `list[dict]` |
| 信号V2 | `hot_stocks`, `concept_blocks`, `daily_dragon_tiger`, `industry_comparison`, `north_money_realtime`, `consensus_eps`, `fund_flow_baidu`, `eastmoney_reports` | 见 [data-types.md](data-types.md) |
| 系统 | `get_status`, `health_check`, `clear_cache`, `tushare` | `dict` / `list[dict]` |

\* `tick_data` / `finance_snapshot` / `f10` 需 **mootdx** 可选依赖。

---

## 6. 原 AkShare 路由覆盖（aggregate）

| 原 FDS 用途 | teak-fds 实现 |
|-------------|----------------|
| 盈利预测 / 公司动态 | `integrations/eastmoney_forecast.py`, `eastmoney_gsrl.py` |
| 公告列表 | 巨潮 `cninfo` + `eastmoney_notice` |
| 机构评级 | `integrations/cninfo_rating.py`（AES） |
| 行业涨跌榜 | `integrations/eastmoney_industry.py` |
| 一致预期 EPS | `integrations/ths_forecast_lite.py`（可选 pandas） |

路由名 `aggregate`；`get_akshare_provider()` 为兼容别名。

---

## 7. 已知限制（验证时可能 SKIP）

| 接口 | 原因 |
|------|------|
| `pe_percentile` / `valuation_percentiles` | 需理杏仁 cookie 有效 |
| `concept_blocks` | 百度失败时走 Tushare；需 Token |
| `industry_comparison` | push2 失败时走 `moneyflow_ind_ths`；需 Token |
| `fund_flow_baidu` | 百度 API 变更时可能为空 |
| `report_rating` | 单股走东财研报；全市场走巨潮按日列表 |
| `consensus_eps` | 同花顺 worth 页；建议 `pip install -e ".[analytics]"` |
| `iwencai` | `pip install -e ".[iwencai]"` + Node.js + `~/agents_documents/IWENCAI_API_KEY.txt` |
| `minute_kline` / `watchlist_stocks` 等 | `~/agents_documents/xueqiu_cookies.txt` |
| `tick_data` | mootdx，验证中为可选 skip |

---

## 8. 返回类型速查（Agent 必遵）

详见 **[data-types.md](data-types.md)**。核心三条：

1. `quote` / `kline` / `valuation` → **dataclass 属性**（`.current`、`.close`）
2. `tushare` / 公告 / 搜索 → **`list[dict]`**
3. 失败 → **`None`**（不要当空列表处理）

CLI `--json` 已将 dataclass 转为 dict；解析时用 stdout，日志在 stderr。

---

## 9. 回归流程（发版 / 改路由后）

1. `python3 -m pytest tests/ -q`
2. `python3 scripts/verify_capabilities.py --json` → 记录 `summary.fail == 0`
3. 抽查 3 条 CLI：`quote`、`kline`、`announcement_list`（巨潮）
4. 更新本文档「最近一次全量参考」数字（若跑全量）

---

## 10. 相关文档

| 文档 | 用途 |
|------|------|
| [install.md](install.md) | 安装与链接 |
| [data-types.md](data-types.md) | 字段级返回约定 |
| [facade.md](facade.md) | API 索引 |
| [routing.md](routing.md) | 数据源优先级 |
| [config.md](config.md) | Token / Cookie 路径 |
