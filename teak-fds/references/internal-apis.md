# 内部 HTTP 实现（无 akshare）

`teakfds/integrations/` 下为原 AkShare 能力区的自研实现：

| 模块 | 能力 | 数据源 |
|------|------|--------|
| `cninfo`（Provider） | 公告列表/PDF | 巨潮 |
| `cninfo_rating` | 投资评级 | 巨潮 webapi + AES |
| `eastmoney_forecast` | 盈利预测 | 东财 datacenter |
| `eastmoney_comment` | 机构参与度 | 东财 datacenter |
| `eastmoney_notice` | 全市场公告 | 东财 np-anotice |
| `eastmoney_gsrl` | 公司动态日历 | 东财 datacenter |
| `eastmoney_industry` | 行业涨跌排名 | 东财 push2 |
| `ths_forecast_lite` | 一致预期 EPS | 同花顺 worth 页（需 `pandas`+`lxml`） |

统一入口：`AggregateProvider`（路由名 `aggregate`）。历史代码中的 `get_akshare_provider()` 仍指向同一实现。

依赖：`requests`、`httpx`、`pycryptodome`（巨潮评级 AES）。可选 `pandas` 用于同花顺 HTML 表解析。
