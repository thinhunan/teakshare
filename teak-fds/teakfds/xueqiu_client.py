"""
雪球 API 客户端 — 统一 cookies 注入、错误处理。

所有 API 请求均自动从 cookies 文件加载 Cookie。
cookies 文件 ~/agents_documents/xueqiu_cookies.txt
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx

from teakfds.datasource_log import get_xueqiu_logger

_logger = get_xueqiu_logger()


def _full_request_url(url: str, params: Optional[Dict[str, Any]]) -> str:
    if not params:
        return url
    return f"{url}?{urlencode(params)}"

# ── Exceptions ──────────────────────────────────────────────

class CookieExpiredError(RuntimeError):
    """cookies 不存在、为空或已被服务端拒绝 (403)"""

class XueqiuRequestError(RuntimeError):
    """请求失败（超时 / 非 200 / 返回异常）"""


# ── Cookies helpers ─────────────────────────────────────────

DEFAULT_COOKIES_TXT = Path.home() / "agents_documents" / "xueqiu_cookies.txt"


def resolve_cookies_path(skill_root: Path) -> Path:
    return DEFAULT_COOKIES_TXT


def _parse_cookie_kv(header: str) -> Dict[str, str]:
    cookies: Dict[str, str] = {}
    for item in header.split(";"):
        item = item.strip()
        if item and "=" in item:
            k, v = item.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies


def _load_cookie_header(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text().strip()


# ── Client ──────────────────────────────────────────────────

@dataclass(frozen=True)
class XueqiuClient:
    cookies_path: Path
    timeout_s: float = 30.0

    @classmethod
    def create(cls, skill_root: Optional[Path] = None, cookies_path: Optional[Path] = None) -> "XueqiuClient":
        if cookies_path:
            return cls(cookies_path=cookies_path)
        root = skill_root or Path(__file__).parent.parent
        return cls(cookies_path=resolve_cookies_path(root))

    # ── internal ────────────────────────────────────────────

    def _headers(self) -> Dict[str, str]:
        cookie_header = _load_cookie_header(self.cookies_path)
        return {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://xueqiu.com/",
            "Cookie": cookie_header,
            "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
            "X-Requested-With": "XMLHttpRequest",
        }

    def _cookies_dict(self) -> Dict[str, str]:
        return _parse_cookie_kv(_load_cookie_header(self.cookies_path))

    def _get_json(self, url: str, params: Optional[Dict[str, Any]] = None, action: str = "request") -> Dict[str, Any]:
        symbol = params.get("symbol") if params else None
        full_url = _full_request_url(url, params)

        header = _load_cookie_header(self.cookies_path)
        if not header:
            _logger.log_error(
                action,
                CookieExpiredError(f"cookies 文件不存在或为空"),
                symbol,
                url=full_url,
                params=params,
            )
            raise CookieExpiredError(f"cookies 文件不存在或为空: {self.cookies_path}")

        t0 = time.perf_counter()
        try:
            with httpx.Client(timeout=self.timeout_s) as c:
                resp = c.get(url, params=params, headers=self._headers(), cookies=self._cookies_dict())
        except httpx.TimeoutException as e:
            _logger.log_request(
                action,
                symbol=symbol,
                success=False,
                message="请求超时",
                url=full_url,
                duration_ms=(time.perf_counter() - t0) * 1000,
                params=params,
            )
            raise XueqiuRequestError(f"请求超时: {url}") from e
        except Exception as e:
            _logger.log_request(
                action,
                symbol=symbol,
                success=False,
                message=f"请求失败: {e}",
                url=full_url,
                duration_ms=(time.perf_counter() - t0) * 1000,
                params=params,
            )
            raise XueqiuRequestError(f"请求失败: {url} ({e})") from e

        elapsed = (time.perf_counter() - t0) * 1000
        final_url = str(resp.url) if resp.url else full_url

        if resp.status_code == 403:
            _logger.log_request(
                action,
                symbol=symbol,
                success=False,
                message="HTTP 403 Cookies过期",
                url=final_url,
                status_code=403,
                duration_ms=elapsed,
                params=params,
            )
            raise CookieExpiredError("HTTP 403 — Cookies 可能已过期，请更新")
        if resp.status_code != 200:
            _logger.log_request(
                action,
                symbol=symbol,
                success=False,
                message=f"HTTP {resp.status_code}",
                url=final_url,
                status_code=resp.status_code,
                duration_ms=elapsed,
                params=params,
            )
            raise XueqiuRequestError(f"HTTP {resp.status_code}: {resp.text[:300]}")

        try:
            data = resp.json()
        except Exception as e:
            _logger.log_request(
                action,
                symbol=symbol,
                success=False,
                message="返回非JSON",
                url=final_url,
                status_code=resp.status_code,
                duration_ms=elapsed,
                params=params,
            )
            raise XueqiuRequestError(f"返回非 JSON: {resp.text[:300]}") from e

        if isinstance(data, dict) and data.get("error_code") not in (None, 0):
            err_msg = f"error_code={data.get('error_code')}: {data.get('error_description')}"
            _logger.log_request(
                action,
                symbol=symbol,
                success=False,
                message=err_msg,
                url=final_url,
                status_code=resp.status_code,
                duration_ms=elapsed,
                params=params,
            )
            raise XueqiuRequestError(f"雪球 {err_msg}")

        _logger.log_request(
            action,
            symbol=symbol,
            success=True,
            message="获取成功",
            url=final_url,
            status_code=resp.status_code,
            duration_ms=elapsed,
            params=params,
        )
        return data  # type: ignore[return-value]

    # ── public API ──────────────────────────────────────────

    def watchlist_stocks(self, *, size: int = 1000, category: int = 1, pid: int = -1) -> Dict[str, Any]:
        """自选股列表"""
        return self._get_json(
            "https://stock.xueqiu.com/v5/stock/portfolio/stock/list.json",
            params={"size": size, "category": category, "pid": pid},
            action="watchlist_stocks",
        )

    def watchlist_cubes(self, *, size: int = 1000, category: int = 1, pid: int = -120) -> Dict[str, Any]:
        """自选组合列表"""
        return self._get_json(
            "https://stock.xueqiu.com/v5/stock/portfolio/stock/list.json",
            params={"size": size, "category": category, "pid": pid},
            action="watchlist_cubes",
        )

    def quote(self, symbol: str, *, extend: str = "detail") -> Dict[str, Any]:
        """个股实时报价与详情"""
        return self._get_json(
            "https://stock.xueqiu.com/v5/stock/quote.json",
            params={"symbol": symbol, "extend": extend},
            action="quote",
        )

    def minute(self, symbol: str, *, period: str = "1d") -> Dict[str, Any]:
        """分时数据"""
        return self._get_json(
            "https://stock.xueqiu.com/v5/stock/chart/minute.json",
            params={"symbol": symbol, "period": period},
            action="minute",
        )

    def kline(
        self,
        symbol: str,
        *,
        begin_ms: Optional[int] = None,
        period: str = "day",
        count: int = 284,
        indicator: str = "kline,pe,pb,ps,pcf,market_capital,agt,ggt,balance",
        kline_type: str = "before",
    ) -> Dict[str, Any]:
        """日线 / 周线 / 月线 K 线数据"""
        if begin_ms is None:
            begin_ms = int(time.time() * 1000)
        return self._get_json(
            "https://stock.xueqiu.com/v5/stock/chart/kline.json",
            params={
                "symbol": symbol,
                "begin": begin_ms,
                "period": period,
                "type": kline_type,
                "count": -abs(int(count)),
                "indicator": indicator,
            },
            action="kline",
        )

    # ── 组合 (cube) API ─────────────────────────────────────

    def cube_rebalancing(
        self,
        cube_symbol: str,
        *,
        count: int = 20,
        page: int = 1,
    ) -> Dict[str, Any]:
        """组合调仓历史"""
        return self._get_json(
            "https://xueqiu.com/cubes/rebalancing/history.json",
            params={"cube_symbol": cube_symbol, "count": count, "page": page},
            action="cube_rebalancing",
        )

    def cube_quote(self, symbol: str) -> Dict[str, Any]:
        """组合/股票批量报价详情（batch quote）"""
        return self._get_json(
            "https://xueqiu.com/service/v5/stock/batch/quote",
            params={"symbol": symbol},
            action="cube_quote",
        )

    def cube_nav(
        self,
        cube_symbol: str,
        *,
        since_ms: Optional[int] = None,
        until_ms: Optional[int] = None,
    ) -> Any:
        """组合净值变化（返回数组，每项含 symbol/name/list）"""
        now = int(time.time() * 1000)
        if until_ms is None:
            until_ms = now
        if since_ms is None:
            since_ms = until_ms - 90 * 86400 * 1000  # 默认最近 90 天
        return self._get_json(
            "https://xueqiu.com/cubes/nav_daily/all.json",
            params={"cube_symbol": cube_symbol, "since": since_ms, "until": until_ms},
            action="cube_nav",
        )

    # ── 财务数据 API (合并自 xueqiu_api) ─────────────────────────────

    def index_quotes(self) -> Dict[str, Any]:
        """首页大盘核心指数行情（上证指数、深证成指、创业板指）- 注意：此接口需要特殊处理"""
        # 雪球指数行情接口需要单独请求每个指数
        symbols = ["SH000001", "SZ399001", "SZ399006"]
        result = {"data": {"items": []}}
        for sym in symbols:
            try:
                quote = self.quote(sym)
                if "data" in quote and "quote" in quote.get("data", {}):
                    result["data"]["items"].append(quote["data"]["quote"])
            except Exception:
                pass
        return result

    def pankou(self, symbol: str) -> Dict[str, Any]:
        """个股盘口分笔数据"""
        return self._get_json(
            "https://stock.xueqiu.com/v5/stock/realtime/pankou.json",
            params={"symbol": symbol},
            action="pankou",
        )

    def capital_flow(self, symbol: str) -> Dict[str, Any]:
        """个股当日分钟级资金流向数据"""
        return self._get_json(
            "https://stock.xueqiu.com/v5/stock/capital/flow.json",
            params={"symbol": symbol},
            action="capital_flow",
        )

    def capital_history(self, symbol: str) -> Dict[str, Any]:
        """个股日级历史资金流向数据"""
        return self._get_json(
            "https://stock.xueqiu.com/v5/stock/capital/history.json",
            params={"symbol": symbol},
            action="capital_history",
        )

    # 注意：财务报表接口 (income/balance/cash_flow) 在 api.xueqiu.com 上被封禁
    # stock.xueqiu.com 不提供这些接口，暂时注释
    # def income_statement(...): ...
    # def balance_sheet(...): ...
    # def cash_flow(...): ...

    def institution_report(self, symbol: str) -> Dict[str, Any]:
        """个股机构评级报告数据 - 注意：可能需要特殊认证"""
        return self._get_json(
            "https://stock.xueqiu.com/v5/stock/report.json",
            params={"symbol": symbol},
            action="institution_report",
        )
