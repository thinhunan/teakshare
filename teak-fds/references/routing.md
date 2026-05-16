# 路由表（摘要）

完整逻辑见 `teakfds/router.py` 中 `Router.ROUTING_RULES` 与 `KLINE_PERIOD_ROUTING`。

## 原则

1. **有非东财源时，东财不在前排**（例如研报列表：`mx_search` → `aggregate` → `eastmoney`）。
2. **A 股 K 线大批量**（`estimated_rows > 500` 或 `large_batch`）：在日线/周/月场景下将 **`qlib` 固定提前**（无 Qlib 则由后续 provider 承接）。

## 常见类型

| 数据类型 | A 股候选顺序（简化） |
|----------|----------------------|
| 实时行情 | tencent → tdx → sina → tushare → mx_data → xueqiu → search_fallback |
| 日线 K 线 | qlib → tushare → tencent → tdx → xueqiu（分钟线不含 qlib） |
| 财务表 | tushare |
| 估值 | lixinger → tushare → xueqiu |
| 搜索/新闻 | mx_search → search_fallback |
| 研报列表 | mx_search → aggregate → eastmoney |
| 龙虎榜 | eastmoney（当前唯一实现，仍为末位生态位） |

`SmartRouter` 会在足够样本后对候选做小幅重排（成功率 + 延迟），不改变「东财靠后」的先验。
