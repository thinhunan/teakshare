# CLI

入口：`teakfds` 或 `python -m teakfds`（需先 `pip install -e .`，见 [install.md](install.md)）。

## 示例

```bash
teakfds quote SH600519 --json
python -m teakfds quote SH600519 --json
python -m teakfds kline SH600519 --period day --count 30 --json
python -m teakfds valuation SH600519 --json
python -m teakfds search "贵州茅台" --type news --json
python -m teakfds status
python -m teakfds health
```

## 输出约定

- **`--json`**：stdout 为 JSON（`QuoteData` / `KlineData` 等已转为 dict/list）
- **无 `--json`**：人类可读表格
- 日志与 Provider 加载信息在 **stderr**，解析 stdout 时不要混入

返回字段含义见 [data-types.md](data-types.md)。
