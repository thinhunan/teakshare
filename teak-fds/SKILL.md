---
name: teak-fds
description: Teak-FDS（teakfds）统一金融数据源：A/H/美股行情、K线、估值与分位（理杏仁）、财务/宏观（Tushare HTTP）、公告研报、妙想搜索、北向等。当用户需要股票/指数金融数据时使用。必须经 TeakFDS 或 CLI 调用，禁止直接 import tushare 或akshare。
---

# Teak-FDS

面向 Agent 的**唯一入口**：`TeakFDS`（别名 `teak-fds`）或 `python -m teakfds`。

## 何时使用

- 实时/历史行情、K 线、估值、财务指标、公告、研报搜索、行业对比、宏观序列等
- 需要**自动选源与降级**（腾讯 / Tushare / 理杏仁 / 巨潮 / 妙想等）

## 快速开始

```python
from teakfds import TeakFDS

fds = TeakFDS()
q = fds.quote("SH600519")           # QuoteData，用 q.current
bars = fds.kline("SH600519", count=5)  # list[KlineData]，用 bars[0].close
rows = fds.tushare("daily", ts_code="600519.SH", start_date="20250501", end_date="20250510")
```

```bash
# 一次性：cd ~/.openclaw/skills/teak-fds && pip install -e .
teakfds quote SH600519 --json
```

## 必读约定（避免歧义）

1. **符号**：门面用 `SH600519` / `SZ000001`；`fds.tushare(..., ts_code='600519.SH')` 用后缀格式。
2. **两种返回形态**：
   - **dataclass**（`quote`, `kline`, `valuation`…）→ 属性访问 + `.to_dict()`
   - **list[dict]**（`tushare`, 公告, 搜索…）→ 字典键访问
3. **失败**：多为 `None`，不要假设空列表。
4. **禁止**：`import tushare` / `import akshare` / 绕过本包直连接口。

字段级说明与实测样本见 **[references/data-types.md](references/data-types.md)**。

## 能力概览

| 类别 | 代表方法 | 优先数据源 |
|------|----------|------------|
| 实时 | `quote`, `batch_quote` | 腾讯 → … |
| K 线 | `kline` | Qlib（大批量日线）/ Tushare / 腾讯 |
| 估值 | `valuation`, `valuation_percentiles` | 理杏仁 → Tushare |
| 财务/宏观 | `tushare`, `income`, `cn_cpi`… | Tushare HTTP |
| 公告 | `announcement_list` | 巨潮 → aggregate |
| 搜索 | `search` | 妙想 |
| 研报/预测 | `report_forecast`, `consensus_eps` | 东财内部 HTTP / 同花顺 |

路由细节：[references/routing.md](references/routing.md)

## 参考文档

| 文档 | 内容 |
|------|------|
| [install.md](references/install.md) | 安装、依赖、测试 |
| [agent-validation.md](references/agent-validation.md) | **Agent 功能验证指南** |
| [config.md](references/config.md) | Token / Cookie 路径 |
| [data-types.md](references/data-types.md) | **返回类型与字段（必读）** |
| [facade.md](references/facade.md) | API 索引 |
| [cli.md](references/cli.md) | 命令行 |
| [routing.md](references/routing.md) | 路由表 |
| [internal-apis.md](references/internal-apis.md) | 内部 HTTP 模块 |
