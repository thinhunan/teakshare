# 配置与凭证

与 `finance-data-source` 保持同一套路径约定，**实现代码未改 token/cookie 解析逻辑**。

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

- 目录：`teakfds/providers/lixinger/`
- `settings.json`：从 `settings.example.json` 复制，填写真实 `accountName` / `password`（JSON 内 `body` 字段）
- `cookie.txt`：可留空，由爬虫在登录成功后写入；若只做只读且已有 cookie，可直接放置有效内容

数据缓存目录默认：`~/agents_documents/lixinger_crawl/db/`（SQLite）。

实现：`teakfds/providers/lixinger/lixinger_spider.py`（自动登录）、`lixinger_provider.py`。

## Qlib（可选）

- 数据目录默认：`~/.qlib/qlib_data/cn_data`
- 需单独 `pip install qlib` 并准备数据

实现：`teakfds/providers/qlib_provider.py`。
