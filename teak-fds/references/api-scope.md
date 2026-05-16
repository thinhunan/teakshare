# 能力边界：为何文档接口少于 AkShare / Tushare 全库

## 三个层次要分清

| 层次 | 是什么 | 规模 |
|------|--------|------|
| **AkShare 全库** | 开源爬虫函数集合，[官方文档](https://akshare.akfamily.xyz/data/index.html) 按站点罗列数百类接口 | **1000+** 独立函数 |
| **Tushare Pro 全库** | 商业数据 API，按 `api_name` 调用 | **数百个** `api_name`（见 Pro 文档 / `api_index`） |
| **Teak-FDS 门面** | Agent 用**统一入口** `TeakFDS`，整合原 **finance-data-source** 能力 + 原 FDS 中经 `akshare` 路由的那部分（现为 `aggregate` 内部 HTTP） | **约 90+** 具名方法 + **`tushare()` 逃生舱** |

Teak-FDS **不是**把 AkShare 源码树搬进仓库，也**不是**把 Tushare 每个接口都封一层 Python 函数。

## Teak-FDS 实际承诺

1. **门面方法**（[facade.md](facade.md)）：原 FDS / 投研 Agent 常用能力，带智能路由、统一符号、统一返回类型。
2. **`fds.tushare(api, **kwargs)`**：访问 **任意** Tushare Pro 已授权接口（参数与官方一致，`ts_code` 用后缀格式）。
3. **禁止** Agent `import akshare` / `import tushare` 绕过本包（路由、限流、日志、凭证路径会失效）。

未在 facade 单独列出的 AkShare 能力，通常属于以下情况之一：

- 原 FDS 从未封装（仅 AkShare 文档有）
- 与投研 Agent 主路径无关（期货、期权、小众宏观站点等）
- 可由 `fds.tushare('某api', ...)` 直接替代

## 如何查「还有没有」某个数据

```python
from teakfds import TeakFDS
fds = TeakFDS()

# 1. 先查门面索引 facade.md
# 2. Tushare：按官方 api 名调用
rows = fds.tushare("moneyflow_hsgt", start_date="20260101", end_date="20260131")

# 3. 看 Provider 是否已加载
fds.get_status()["providers"]
```

## 文档维护原则

- **SKILL.md**：何时用 + 全量门面方法索引（一句话说明）
- **facade.md**：每方法返回类型 + 说明 + 注意事项
- **cli.md**：已注册 CLI；无 CLI 的写 Python 示例
- **data-types.md**：返回字段契约

新增门面方法时，须同步更新以上四份文档。
