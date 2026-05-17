# Teak-FDS (teakfds)

面向 AI Agent 的**统一 A/H/美股金融数据门面**：行情、K 线、估值与分位、财务三表、公告研报、资金流、宏观与 Tushare 逃生舱。**不依赖 akshare**，内部以 HTTP 聚合东财/巨潮/腾讯/理杏仁/雪球/Tushare 等。

- **当前版本**：1.0.5
- **Python**：≥ 3.9
- **技能文档**：[SKILL.md](SKILL.md)（Agent 何时调用）
- **API 索引**：[references/facade.md](references/facade.md)
- **返回类型**：[references/data-types.md](references/data-types.md)

## 快速开始

```bash
cd teak-fds
pip install -e .

# 推荐可选能力
pip install -e ".[analytics]"   # 同花顺一致预期 EPS
pip install -e ".[iwencai]"     # 问财 NL 选股（需 Node.js）
pip install -e ".[qlib]"        # 本地日线大批量
# pip install -e ".[mootdx]"    # 通达信逐笔/F10（可选，当前验证不强制）

python -c "from teakfds import TeakFDS; print(TeakFDS().quote('SH600519'))"
teakfds quote SH600519 --json
```

## 凭证（统一路径）

所有路径由 `teakfds/credentials.py` 解析，默认在 `~/agents_documents/`：

| 用途 | 文件 | 环境变量 |
|------|------|----------|
| Tushare Pro | `TUSHARE_TOKEN.txt` | `TUSHARE_TOKEN` |
| 雪球 | `xueqiu_cookies.txt` | — |
| 妙想搜索 | `MX_APIKEY.txt` | `MX_APIKEY` |
| 问财 (pywencai) | `IWENCAI_API_KEY.txt` | —（内容为浏览器 Cookie 头） |
| 理杏仁 | `teakfds/providers/lixinger/settings.json` + `cookie.txt` | 技能内，可自动登录 |

详见 [references/config.md](references/config.md)、[references/install.md](references/install.md)。

## 验证（发版前建议跑）

```bash
# 91 个门面方法 + 字段语义（dividend.amount、money_flow.main_net 等）
python scripts/verify_all_apis.py --strict
python scripts/verify_all_apis.py --strict --symbol SH600519,SZ300750

# 88 项分类冒烟
python scripts/verify_capabilities.py

pytest tests/ -q
```

### 关于验证中的 SKIP

| 类型 | 说明 |
|------|------|
| **mootdx 逐笔** | `tick_data` / `tick_data_history` — 需本地通达信；**当前不纳入必过项** |
| **tdx 深度** | `depth` / `f10` / `finance_snapshot` / `xdxr` — 无 mootdx 时为 None |
| **Tushare 权限** | `stk_mins` 等需高积分接口 |
| **理杏仁** | 分位/历史估值 — 需有效 `settings.json`；首次可能自动登录 |
| **全市场类** | 龙虎榜/宏观/部分搜索 — 非交易时段或接口限流可为空 |
| **问财** | 需 `pip install -e ".[iwencai]"`、本机 **Node.js**、`IWENCAI_API_KEY.txt` |
| **妙想** | `search*` — 需 `MX_APIKEY.txt` |

已配置 **雪球 cookie** 时，`minute_kline` / `pankou` / `capital_flow` / `watchlist_stocks` / `intraday` 等应能通过严格验证。

## 项目结构

```
teak-fds/
├── SKILL.md                 # Agent 技能入口
├── README.md                # 本文件
├── pyproject.toml
├── scripts/
│   ├── verify_all_apis.py   # 全量 API + 语义契约
│   └── verify_capabilities.py
├── references/              # install / facade / cli / routing
├── tests/
└── teakfds/
    ├── finance_data_source.py   # TeakFDS 门面
    ├── credentials.py           # 凭证路径统一
    ├── normalize_finance.py     # 字段归一化（amount、main_net 等）
    ├── api_semantics.py         # 验证用语义规则
    ├── providers/               # 多数据源 Provider
    └── integrations/            # 东财/巨潮/同花顺等 HTTP 实现
```

## OpenClaw / Cursor 技能

将本目录链到技能路径（须为**目录实体**或技能根内相对链接，勿链到仓库外路径以免 `symlink-escape`）：

```bash
ln -sfn /path/to/teakshare/teak-fds ~/.openclaw/skills/teak-fds
pip install -e ~/.openclaw/skills/teak-fds
```

## 许可

MIT
