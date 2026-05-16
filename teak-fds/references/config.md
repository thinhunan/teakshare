# 配置与凭证

Teak-FDS **自包含**，凭证与配置文件均放在本技能目录或 `~/agents_documents/`，**不依赖** `finance-data-source` 或 `akshare` 仓库路径。

## Tushare

- 文件（行内纯文本 token）：`~/agents_documents/TUSHARE_TOKEN.txt`
- 备选：`~/.openclaw/credentials/TUSHARE_TOKEN.txt`、`~/.tushare/token.txt`
- 环境变量：`TUSHARE_TOKEN` 优先于文件

实现：`teakfds/tushare_lite.py` → `load_tushare_token`。

## 雪球

- Cookie 文本：`~/agents_documents/xueqiu_cookies.txt`（浏览器导出或一行 Cookie 头）

实现：`teakfds/xueqiu_client.py` → `XueqiuClient`。

## 妙想（MX）

- `~/agents_documents/MX_APIKEY.txt` 或环境变量 `MX_APIKEY`

实现：`teakfds/providers/mx_search_provider.py`。

## 理杏仁

**唯一配置目录**：`teakfds/providers/lixinger/`（技能内，已 gitignore 敏感文件）

| 文件 | 说明 |
|------|------|
| `settings.json` | 从 `settings.example.json` 复制并填写 `accountName` / `password`（勿提交 git） |
| `cookie.txt` | 可留空；登录成功后自动写入；失效后自动重新登录 |

失效后爬虫会 **自动登录并写回 cookie**；API 认证失败时 **重新登录并重试一次**（`lixinger_spider._request`）。

**首次从旧环境迁移（一次性）**：

```bash
cp /path/to/old/lixinger/settings.json ~/.openclaw/skills/teak-fds/teakfds/providers/lixinger/
# cookie.txt 可选，留空则会自动登录生成
```

数据缓存目录默认：`~/agents_documents/lixinger_crawl/db/`（SQLite）。

实现：`teakfds/providers/lixinger/lixinger_spider.py`、`lixinger_provider.py`。

## Qlib（可选）

- 数据目录默认：`~/.qlib/qlib_data/cn_data`
- 需单独 `pip install qlib` 并准备数据

实现：`teakfds/providers/qlib_provider.py`。
