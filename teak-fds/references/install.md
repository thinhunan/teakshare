# 安装与运行

## 技能目录（符号链接）

本仓库已链到 Agent 技能目录（任选其一维护即可，指向同一目录）：

- `~/.agents/skills/teak-fds`
- `~/.openclaw/skills/teak-fds`

更新代码只需改仓库内 `teak-fds/`，链接自动生效。

## 一次性安装（必需）

在技能根目录执行**一次**可编辑安装，之后任意目录可直接 `import teakfds` 或调用 `teakfds` CLI，**无需**设置 `PYTHONPATH`：

```bash
cd ~/.openclaw/skills/teak-fds   # 或 ~/.agents/skills/teak-fds
pip install -e .
```

验证：

```bash
python -c "from teakfds import TeakFDS; print(TeakFDS().quote('SH600519'))"
teakfds quote SH600519 --json
python -m teakfds quote SH600519 --json
```

## Python 版本

`requires-python >= 3.9`

## 依赖

### 必需（`pip install -e .` 会自动安装）

| 包 | 用途 |
|----|------|
| `requests` | 东财/巨潮/腾讯等 HTTP |
| `httpx` | 雪球 |
| `pycryptodome` | 巨潮 webapi 评级 AES |

### 可选 extras

```bash
pip install -e ".[analytics]"   # pandas + lxml：同花顺 worth 页一致预期 EPS
pip install -e ".[mootdx]"      # 通达信行情
pip install -e ".[qlib]"        # 本地 A 股日线大批量（需 ~/.qlib/qlib_data/cn_data）
pip install -e ".[dev]"         # pytest
```

## 凭证文件

路径与说明见 [config.md](config.md)。无 Token 时：行情/部分东财接口仍可用；Tushare/妙想/理杏仁/雪球按接口降级或返回 `None`。

## 自检

```bash
cd ~/.openclaw/skills/teak-fds
python3 -m pytest tests/ -q -m "not integration"    # 离线
python3 -m pytest tests/ -q -m integration         # 联网（需 Token/网络）
```

## 日志

外呼请求 JSON 行日志：`~/.openclaw/logs/dataproxy/dataproxy.log`  
内部诊断：`stderr`（不污染 CLI 的 `--json` stdout）。
