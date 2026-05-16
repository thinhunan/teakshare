#!/usr/bin/env python3
"""
TencentProvider - 腾讯财经实时行情
P0级别 - A股/港股/美股实时行情主源

⚠️ 限流要求: ≤2次/秒 (minimum_interval = 0.5秒)
"""

import requests
import time
import json
from typing import Optional, List, Dict, Any
from datetime import datetime

import sys
import time
from pathlib import Path

# 添加路径支持多种导入方式
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from teakfds.datasource_log import log_external_request

from teakfds.providers.base_provider import BaseProvider, ProviderCapabilities
from teakfds.models import QuoteData, DepthData, KlineData, IntradayData, ProviderStatus


class RateLimiter:
    """
    限流器 - 确保调用频率不超过限制
    
    腾讯财经限制: ≤2次/秒
    """
    
    def __init__(self, min_interval: float = 0.5):
        """
        Args:
            min_interval: 最小调用间隔(秒)，默认0.5秒（即2次/秒）
        """
        self.min_interval = min_interval
        self.last_request_time = 0
        self.request_count = 0
        self.lock = None  # 线程锁，如需多线程可添加threading.Lock()
    
    def wait(self):
        """等待直到可以发送下一个请求"""
        now = time.time()
        elapsed = now - self.last_request_time
        
        if elapsed < self.min_interval:
            sleep_time = self.min_interval - elapsed
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
        self.request_count += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """获取限流统计"""
        return {
            "min_interval": self.min_interval,
            "max_rate": f"{1/self.min_interval:.1f}次/秒",
            "request_count": self.request_count
        }


class TencentProvider(BaseProvider):
    """
    腾讯财经数据源Provider - P0级别实时行情主源
    
    ⚠️ 限流配置:
    - 调用间隔: minimum_interval = 0.5秒
    - 最大频率: ≤2次/秒
    - 批量查询: 一次最多查询多只股票（减少API调用）
    
    支持功能:
    - 实时行情 (quote/batch_quote)
    - 五档盘口 (depth)
    - 分时数据 (intraday)
    - K线数据 (kline)
    """
    
    name = "tencent"
    display_name = "腾讯财经"
    priority = 100
    
    capabilities = ProviderCapabilities(
        supports_quote=True,
        supports_depth=True,
        supports_intraday=True,
        supports_kline=True,
        supports_money_flow=True,
        markets=['a_share', 'hk', 'us'],
        kline_periods=['1min', '5min', '15min', '30min', '60min', 'day', 'week', 'month']
    )
    
    # API URL
    QUOTE_URL = "https://qt.gtimg.cn/q="
    KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    INTRADAY_URL = "https://web.ifzq.gtimg.cn/appstock/app/minute/query"
    # 证券名称 / 代码互查（smartbox，JSON）
    SMARTBOX_SEARCH_URL = "https://proxy.finance.qq.com/cgi/cgi-bin/smartbox/search"
    # smartbox 股票条目的 type：GP-A=A 股，GP=港/美等普通股；同名可多条并存（如 A+H）
    SMARTBOX_EQUITY_TYPES = frozenset({"GP", "GP-A"})
    
    def __init__(self):
        super().__init__()
        # ⚠️ 腾讯财经限流: 0.5秒间隔 = 2次/秒
        self.rate_limiter = RateLimiter(min_interval=0.5)
        self._request_count = 0
    
    def _make_request(
        self,
        url: str,
        params: Dict = None,
        timeout: int = 5,
        headers: Optional[Dict[str, str]] = None,
    ) -> Optional[requests.Response]:
        """
        发送请求（带限流控制）
        
        Args:
            url: 请求URL
            params: URL参数
            timeout: 超时时间
            headers: 可选请求头（如 smartbox 需浏览器 UA）
        
        Returns:
            Response对象或None
        """
        # 限流等待
        self.rate_limiter.wait()

        t0 = time.perf_counter()
        try:
            kw = {"timeout": timeout}
            if params is not None:
                kw["params"] = params
            if headers:
                kw["headers"] = headers
            resp = requests.get(url, **kw)
            self._request_count += 1
            elapsed = (time.perf_counter() - t0) * 1000
            final = str(resp.url) if resp is not None else url
            log_external_request(
                provider="tencent",
                method="GET",
                url=final,
                action="http",
                success=resp.status_code == 200,
                status_code=resp.status_code,
                duration_ms=elapsed,
                message="ok" if resp.status_code == 200 else resp.text[:200] if resp.text else "",
                params=dict(params) if params else None,
                caller="TencentProvider._make_request",
            )
            return resp
        except Exception as e:
            log_external_request(
                provider="tencent",
                method="GET",
                url=url,
                action="http",
                success=False,
                message=str(e)[:800],
                duration_ms=(time.perf_counter() - t0) * 1000,
                params=dict(params) if params else None,
                caller="TencentProvider._make_request",
            )
            print(f"TencentProvider request error: {e}")
            return None
    
    def is_available(self) -> bool:
        """检查Provider是否可用"""
        try:
            resp = self._make_request(f"{self.QUOTE_URL}sh600519", timeout=3)
            return resp is not None and resp.status_code == 200
        except:
            return False
    
    def get_status(self) -> ProviderStatus:
        """获取Provider状态"""
        available = self.is_available()
        return ProviderStatus(
            name=self.name,
            available=available,
            last_success=datetime.now().isoformat() if available else None,
            avg_latency_ms=self._test_latency(),
        )
    
    def _test_latency(self) -> float:
        """测试延迟"""
        start = time.time()
        try:
            resp = self._make_request(f"{self.QUOTE_URL}sh600519", timeout=3)
            if resp and resp.status_code == 200:
                return (time.time() - start) * 1000
        except:
            pass
        return -1
    
    def _convert_symbol(self, symbol: str, is_index: bool = False) -> str:
        """
        转换股票代码为腾讯财经格式

        Args:
            symbol: 原始股票代码 (如 'SH600519', '600519', '00700.HK', 'AAPL')
            is_index: 是否为指数代码（显式指定）。若为 True，000xxx → sh，399xxx → sz。
                      若为 False（默认），使用自动判断：已知指数代码（000300等）自动识别。

        Returns:
            腾讯格式代码 (如 'sh600519', 'hk00700', 'usAAPL')
        """
        symbol = symbol.upper().strip()

        # A股: SH600519 -> sh600519
        if symbol.startswith('SH'):
            return f"sh{symbol[2:]}"
        if symbol.startswith('SZ'):
            return f"sz{symbol[2:]}"
        if symbol.startswith('BJ'):
            return f"bj{symbol[2:]}"

        # A股: 600519.SH -> sh600519
        if symbol.endswith('.SH'):
            return f"sh{symbol[:-3]}"
        if symbol.endswith('.SZ'):
            return f"sz{symbol[:-3]}"
        if symbol.endswith('.BJ'):
            return f"bj{symbol[:-3]}"

        # 港股: 00700.HK -> hk00700
        if '.HK' in symbol or symbol.startswith('HK'):
            code = symbol.replace('.HK', '').replace('HK', '')
            return f"hk{code.zfill(5)}"

        # 已知上交所指数代码（无股票冲突的）
        SH_INDEX_CODES = {'000300', '000016', '000905', '000852', '000688', '000903', '000819'}
        # 已知深交所指数代码
        SZ_INDEX_CODES = {'399001', '399006', '399673', '399102'}

        # A股: 6位数字代码自动判断交易所
        if len(symbol) == 6 and symbol.isdigit():
            # 显式指定为指数
            if is_index:
                if symbol.startswith('399'):
                    return f"sz{symbol}"
                return f"sh{symbol}"

            # 自动检测：已知指数代码
            if symbol in SH_INDEX_CODES:
                return f"sh{symbol}"
            if symbol in SZ_INDEX_CODES:
                return f"sz{symbol}"

            # 股票代码：6/5/9 开头为沪市
            if symbol.startswith(('6', '5', '9')):
                return f"sh{symbol}"
            else:
                return f"sz{symbol}"

        # 美股: AAPL -> usAAPL
        return f"us{symbol}"

    @staticmethod
    def _smartbox_raw_code_to_fds_symbol(raw: str) -> str:
        """
        smartbox 返回的 code（如 sh600519、hk00700、usAAPL）→ FDS 常用写法（SH600519、HK00700、AAPL）。
        """
        if not raw:
            return ""
        r = raw.strip().lower()
        if r.startswith("sh") and len(r) > 2:
            return "SH" + r[2:].upper()
        if r.startswith("sz") and len(r) > 2:
            return "SZ" + r[2:].upper()
        if r.startswith("bj") and len(r) > 2:
            return "BJ" + r[2:].upper()
        if r.startswith("hk") and len(r) > 2:
            return "HK" + r[2:].upper()
        if r.startswith("us") and len(r) > 2:
            return r[2:].upper()
        return raw.strip().upper()

    @staticmethod
    def normalize_smartbox_market(market: Optional[str]) -> Optional[str]:
        """
        名称→代码时的「市场」参数：``None`` 表示按 smartbox 返回顺序取第一条 **GP/GP-A** 标的；
        否则取 ``a_share`` / ``hk`` / ``us``。
        """
        if market is None:
            return None
        s = str(market).strip().lower()
        if s in ("", "auto", "default", "first"):
            return None
        if s in ("a_share", "a", "cn", "ashare", "a股"):
            return "a_share"
        if s in ("hk", "h", "hk_share", "hongkong", "港股"):
            return "hk"
        if s in ("us", "u", "us_share", "美股", "ny", "nasdaq"):
            return "us"
        return None

    def _smartbox_fetch_stock_items(self, query: str) -> Optional[List[dict]]:
        """请求 smartbox，返回 ``stock`` 列表；失败为 ``None``。"""
        q = (query or "").strip()
        if not q:
            return None
        params = {
            "stockFlag": "1",
            "fundFlag": "0",
            "app": "official_website",
            "query": q,
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
        }
        resp = self._make_request(
            self.SMARTBOX_SEARCH_URL,
            params=params,
            timeout=10,
            headers=headers,
        )
        if not resp or resp.status_code != 200 or not resp.text:
            return None
        try:
            data = resp.json()
        except Exception:
            try:
                data = json.loads(resp.text)
            except Exception:
                return None
        stocks = data.get("stock") or []
        return stocks if stocks else None

    @staticmethod
    def _filter_smartbox_equity_rows(stocks: List[dict]) -> List[dict]:
        """仅保留 type 为 GP / GP-A 的股票条目（保持接口原始顺序）。"""
        out: List[dict] = []
        for s in stocks:
            t = (s.get("type") or "").strip()
            if t in TencentProvider.SMARTBOX_EQUITY_TYPES:
                out.append(s)
        return out

    def _select_smartbox_equity_row(
        self,
        equity_rows: List[dict],
        all_stocks: List[dict],
        market: Optional[str],
    ) -> Optional[dict]:
        """
        ``market`` 为 ``normalize_smartbox_market`` 的结果：``None`` | ``a_share`` | ``hk`` | ``us``。
        """
        if market is None:
            if equity_rows:
                return equity_rows[0]
            return all_stocks[0] if all_stocks else None
        if market == "a_share":
            for s in equity_rows:
                if (s.get("type") or "").strip() == "GP-A":
                    return s
            for s in equity_rows:
                raw = (s.get("code") or "").strip().lower()
                if raw.startswith(("sh", "sz", "bj")):
                    return s
            return None
        if market == "hk":
            for s in equity_rows:
                raw = (s.get("code") or "").strip().lower()
                if raw.startswith("hk"):
                    return s
            return None
        if market == "us":
            for s in equity_rows:
                raw = (s.get("code") or "").strip().lower()
                if raw.startswith("us"):
                    return s
            return None
        return None

    def smartbox_resolve_stock(
        self, query: str, market: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        腾讯财经 smartbox：按名称或关键词搜索，在 **GP / GP-A** 结果中解析一条证券。

        - ``market is None``：取 smartbox 返回的 **第一条** GP/GP-A（与接口 ``stock`` 顺序一致）。
        - ``market`` 为 ``a_share`` / ``hk`` / ``us``：在该顺序下取对应市场的第一条（如 A+H 同名时指定港股）。

        GET https://proxy.finance.qq.com/cgi/cgi-bin/smartbox/search

        Returns:
            ``{"code": "SH600519", "name": "...", "raw_code": "sh600519", "smartbox_type": "GP-A"}`` 或 None
        """
        q = (query or "").strip()
        if not q:
            return None
        m = self.normalize_smartbox_market(market)
        stocks = self._smartbox_fetch_stock_items(q)
        if not stocks:
            return None
        equity_rows = self._filter_smartbox_equity_rows(stocks)
        row = self._select_smartbox_equity_row(equity_rows, stocks, m)
        if not row:
            return None
        raw_code = (row.get("code") or "").strip()
        name = (row.get("name") or "").strip()
        code = self._smartbox_raw_code_to_fds_symbol(raw_code)
        if not code:
            return None
        out: Dict[str, Any] = {"code": code, "name": name, "raw_code": raw_code}
        t = (row.get("type") or "").strip()
        if t:
            out["smartbox_type"] = t
        return out

    def smartbox_first_stock(self, query: str) -> Optional[Dict[str, str]]:
        """
        腾讯财经 smartbox：按名称或代码搜索，取 **第一条 GP/GP-A 证券**（等价于 ``smartbox_resolve_stock(query, None)``）。

        GET https://proxy.finance.qq.com/cgi/cgi-bin/smartbox/search

        Returns:
            ``{"code": "SH600519", "name": "贵州茅台"}`` 或 None
        """
        hit = self.smartbox_resolve_stock(query, None)
        return hit
    
    def _parse_quote_response(self, text: str, symbol: str) -> Optional[QuoteData]:
        """解析行情响应"""
        try:
            if not text or '~' not in text:
                return None
            
            parts = text.split('~')
            if len(parts) < 45:
                return None
            
            name = parts[1]
            code = parts[2]
            current = float(parts[3]) if parts[3] else 0
            yesterday_close = float(parts[4]) if parts[4] else 0
            open_price = float(parts[5]) if parts[5] else 0
            volume = int(float(parts[6])) if parts[6] else 0
            high = float(parts[33]) if len(parts) > 33 and parts[33] else 0
            low = float(parts[34]) if len(parts) > 34 and parts[34] else 0
            amount = float(parts[37]) if len(parts) > 37 and parts[37] else 0
            
            percent = 0
            if yesterday_close > 0:
                percent = (current - yesterday_close) / yesterday_close * 100

            # 扩展字段: PE/PB/换手率/市值/量比
            def _safe_float(idx, default=None):
                try:
                    if len(parts) > idx and parts[idx]:
                        return float(parts[idx])
                except (ValueError, IndexError):
                    pass
                return default

            turnover_rate = _safe_float(38)
            pe_ttm = _safe_float(39)
            circulating_market_cap = _safe_float(44)
            total_market_cap = _safe_float(45)
            pb = _safe_float(46)
            volume_ratio = _safe_float(49)

            # 市值单位: 腾讯返回的流通市值/总市值字段单位是亿元，无需转换
            # (实测: SH600519茅台 total_market_cap ≈ 17341 对应约1.7万亿市值)
            
            return QuoteData(
                symbol=symbol,
                name=name,
                current=current,
                open=open_price,
                high=high,
                low=low,
                close=yesterday_close,
                volume=volume * 100,
                amount=amount * 10000,
                percent=percent,
                timestamp=datetime.now().isoformat(),
                source=self.name,
                pe_ttm=pe_ttm,
                pb=pb,
                turnover_rate=turnover_rate,
                total_market_cap=total_market_cap,
                circulating_market_cap=circulating_market_cap,
                volume_ratio=volume_ratio,
            )
        except Exception as e:
            print(f"Parse quote error: {e}")
            return None
    
    def quote(self, symbol: str) -> Optional[QuoteData]:
        """
        获取实时行情（带限流控制）
        
        Args:
            symbol: 股票代码
        
        Returns:
            QuoteData对象或None
        """
        try:
            qt_symbol = self._convert_symbol(symbol)
            url = f"{self.QUOTE_URL}{qt_symbol}"
            
            resp = self._make_request(url, timeout=5)
            if not resp or resp.status_code != 200:
                return None
            
            return self._parse_quote_response(resp.text, symbol)
            
        except Exception as e:
            print(f"TencentProvider.quote error: {e}")
            return None
    
    def batch_quote(self, symbols: List[str]) -> List[QuoteData]:
        """
        批量获取实时行情（优化API调用）
        
        ⚠️ 重要: 批量查询只需一次API调用，大幅节省配额
        
        Args:
            symbols: 股票代码列表
        
        Returns:
            QuoteData列表
        """
        if not symbols:
            return []
        
        try:
            qt_symbols = [self._convert_symbol(s) for s in symbols]
            url = f"{self.QUOTE_URL}{','.join(qt_symbols)}"
            
            resp = self._make_request(url, timeout=10)
            if not resp or resp.status_code != 200:
                return []
            
            results = []
            lines = resp.text.strip().split('\n')
            
            for i, line in enumerate(lines):
                if i >= len(symbols):
                    continue
                
                quote = self._parse_quote_response(line, symbols[i])
                if quote:
                    results.append(quote)
            
            return results
            
        except Exception as e:
            print(f"TencentProvider.batch_quote error: {e}")
            return []
    
    def depth(self, symbol: str) -> Optional[DepthData]:
        """
        获取五档盘口
        
        Args:
            symbol: 股票代码
        
        Returns:
            DepthData对象或None
        """
        try:
            qt_symbol = self._convert_symbol(symbol)
            url = f"{self.QUOTE_URL}{qt_symbol}"
            
            resp = self._make_request(url, timeout=5)
            if not resp or resp.status_code != 200:
                return None
            
            text = resp.text.strip()
            if not text or '~' not in text:
                return None
            
            parts = text.split('~')
            if len(parts) < 50:
                return None
            
            # 解析买卖五档
            # 腾讯格式: 买盘价格~买盘数量~卖盘价格~卖盘数量...
            bids = []
            asks = []
            
            # 买卖盘数据位置 (根据腾讯API格式)
            # 卖5价~卖5量~卖4价~卖4量~...~卖1价~卖1量~买1价~买1量~...~买5价~买5量
            # 大致从索引9开始
            try:
                # 买盘 (买1到买5)
                for i in range(5):
                    price_idx = 9 + i * 2
                    vol_idx = 10 + i * 2
                    if price_idx < len(parts) and vol_idx < len(parts):
                        price = float(parts[price_idx]) if parts[price_idx] else 0
                        volume = int(float(parts[vol_idx])) if parts[vol_idx] else 0
                        if price > 0:
                            bids.append({"price": price, "volume": volume})
                
                # 卖盘 (卖1到卖5) - 卖盘在买盘之前
                for i in range(5):
                    price_idx = 19 + i * 2
                    vol_idx = 20 + i * 2
                    if price_idx < len(parts) and vol_idx < len(parts):
                        price = float(parts[price_idx]) if parts[price_idx] else 0
                        volume = int(float(parts[vol_idx])) if parts[vol_idx] else 0
                        if price > 0:
                            asks.insert(0, {"price": price, "volume": volume})  # 卖1在列表前面
            
            except Exception as e:
                print(f"Parse depth error: {e}")
            
            return DepthData(
                symbol=symbol,
                bids=bids,
                asks=asks,
                timestamp=datetime.now().isoformat(),
                source=self.name
            )
            
        except Exception as e:
            print(f"TencentProvider.depth error: {e}")
            return None
    
    def intraday(self, symbol: str) -> Optional[List[IntradayData]]:
        """
        获取分时数据
        
        Args:
            symbol: 股票代码
        
        Returns:
            IntradayData列表或None
        """
        try:
            qt_symbol = self._convert_symbol(symbol)
            
            params = {
                'code': qt_symbol,
                '_': int(time.time() * 1000)
            }
            
            resp = self._make_request(self.INTRADAY_URL, params=params, timeout=10)
            if not resp or resp.status_code != 200:
                return None
            
            data = resp.json()
            
            # 解析分时数据
            code_key = qt_symbol
            if code_key not in data.get('data', {}):
                return None
            
            minute_data = data['data'][code_key].get('data', {})
            minute_list = minute_data.get('data', [])
            
            intraday_list = []
            for item in minute_list:
                try:
                    # 格式: [时间, 价格, 均价, 成交量]
                    if len(item) >= 4:
                        intraday_list.append(IntradayData(
                            time=str(item[0]),
                            price=float(item[1]),
                            avg_price=float(item[2]),
                            volume=int(item[3]),
                            amount=float(item[1]) * int(item[3]) * 100,
                        ))
                except Exception:
                    continue
            
            return intraday_list
            
        except Exception as e:
            print(f"TencentProvider.intraday error: {e}")
            return None
    
    def kline(self, 
              symbol: str, 
              period: str = 'day',
              count: int = 30,
              start_date: str = None,
              end_date: str = None) -> Optional[List[KlineData]]:
        """
        获取K线数据
        
        Args:
            symbol: 股票代码
            period: 周期 ('1min', '5min', '15min', '30min', '60min', 'day', 'week', 'month')
            count: 获取条数
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)
        
        Returns:
            KlineData列表或None
        """
        try:
            qt_symbol = self._convert_symbol(symbol)
            
            # 周期映射 (支持分钟K线)
            period_map = {
                '1min': 'm1',
                '5min': 'm5',
                '15min': 'm15',
                '30min': 'm30',
                '60min': 'm60',
                'day': 'day',
                'week': 'week',
                'month': 'month'
            }
            
            if period not in period_map:
                print(f"Unsupported period: {period}")
                return None
            
            tencent_period = period_map[period]

            # 腾讯 K 线接口 param 格式：code,period,start,end,count,fq_type
            # 注意：start/end 为空时需用两个连续逗号占位
            params = {
                'param': f"{qt_symbol},{tencent_period},,,{count},qfq",
                '_': int(time.time() * 1000)
            }

            resp = self._make_request(self.KLINE_URL, params=params, timeout=10)
            if not resp or resp.status_code != 200:
                return None

            data = resp.json()

            code_key = qt_symbol
            if code_key not in data.get('data', {}):
                return None

            kline_data = data['data'][code_key]
            # 复权 K 线的 key 为 qfqday / qfqweek / qfqmonth；非复权才是 day/week/month
            candidate_keys = [f"qfq{tencent_period}", tencent_period]
            kline_key = next((k for k in candidate_keys if k in kline_data), None)
            if not kline_key:
                return None
            
            klines = []
            for item in kline_data[kline_key]:
                try:
                    # 格式: [日期, 开盘, 收盘, 最低, 最高, 成交量]
                    if len(item) >= 6:
                        klines.append(KlineData(
                            date=str(item[0]),
                            open=float(item[1]),
                            high=float(item[4]),
                            low=float(item[3]),
                            close=float(item[2]),
                            volume=int(float(item[5])),
                            amount=float(item[6]) if len(item) > 6 and item[6] else 0,
                        ))
                except Exception:
                    continue
            
            return klines
            
        except Exception as e:
            print(f"TencentProvider.kline error: {e}")
            return None
    
    def get_rate_limit_stats(self) -> Dict[str, Any]:
        """获取限流统计信息"""
        return {
            "provider": self.name,
            "request_count": self._request_count,
            **self.rate_limiter.get_stats()
        }

    # ========== 资金流向 (ff_ 前缀) ==========

    def money_flow(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        获取资金流向 (Tencent ff_ 前缀)

        Note: ff_ 前缀对A股不可用，仅对部分市场有效。
        A股资金流向请使用 tushare/mx_data/xueqiu 数据源。

        Args:
            symbol: 股票代码

        Returns:
            dict with main_inflow, main_outflow, main_net, etc. or None
        """
        try:
            qt_symbol = self._convert_symbol(symbol)
            ff_symbol = f"ff_{qt_symbol}"
            url = f"{self.QUOTE_URL}{ff_symbol}"

            resp = self._make_request(url, timeout=5)
            if not resp or resp.status_code != 200:
                return None

            text = resp.text.strip()
            if not text or '~' not in text or 'none_match' in text:
                return None

            # 去除变量前缀 v_ff_sh600519="..."
            if '=' in text and '"' in text:
                text = text.split('"')[1]

            parts = text.split('~')
            if len(parts) < 12:
                return None

            def _safe_float(idx):
                try:
                    return float(parts[idx]) if len(parts) > idx and parts[idx] else 0
                except (ValueError, IndexError):
                    return 0

            result = {
                'symbol': symbol,
                'main_inflow': _safe_float(2),
                'main_outflow': _safe_float(3),
                'main_net': _safe_float(4),
                'retail_inflow': _safe_float(5),
                'retail_outflow': _safe_float(6),
                'retail_net': _safe_float(7),
                'total_amount': _safe_float(12),
                'source': self.name,
            }
            return result

        except Exception as e:
            print(f"TencentProvider.money_flow error: {e}")
            return None

    # ========== 盘口分析 (s_pk 前缀) ==========

    def pankou_analysis(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        获取盘口分析 (Tencent s_pk 前缀)

        Returns: dict with buy_big_pct, buy_small_pct, sell_big_pct, sell_small_pct
        """
        try:
            qt_symbol = self._convert_symbol(symbol)
            pk_symbol = f"s_pk{qt_symbol}"
            url = f"{self.QUOTE_URL}{pk_symbol}"

            resp = self._make_request(url, timeout=5)
            if not resp or resp.status_code != 200:
                return None

            text = resp.text.strip()
            if not text or '~' not in text:
                return None

            # 去除变量前缀 v_s_pksh600519="..."
            if '=' in text and '"' in text:
                text = text.split('"')[1]

            parts = text.split('~')
            if len(parts) < 4:
                return None

            def _safe_float(idx):
                try:
                    return float(parts[idx]) if len(parts) > idx and parts[idx] else 0
                except (ValueError, IndexError):
                    return 0

            return {
                'symbol': symbol,
                'buy_big_pct': _safe_float(0),    # 买盘大单比例
                'buy_small_pct': _safe_float(1),  # 买盘小单比例
                'sell_big_pct': _safe_float(2),   # 卖盘大单比例
                'sell_small_pct': _safe_float(3), # 卖盘小单比例
                'source': self.name,
            }

        except Exception as e:
            print(f"TencentProvider.pankou_analysis error: {e}")
            return None


# 全局实例
_tencent_provider: Optional[TencentProvider] = None


def get_tencent_provider() -> TencentProvider:
    """获取TencentProvider全局实例"""
    global _tencent_provider
    if _tencent_provider is None:
        _tencent_provider = TencentProvider()
    return _tencent_provider


if __name__ == '__main__':
    print("Testing TencentProvider...")
    print(f"⚠️ 限流配置: ≤2次/秒 (0.5秒间隔)\n")
    
    provider = TencentProvider()
    
    print(f"Available: {provider.is_available()}")
    print(f"Rate Limit: {provider.get_rate_limit_stats()}")
    
    # 测试quote
    print("\n测试实时行情:")
    quote = provider.quote('SH600519')
    if quote:
        print(f"  {quote.symbol}: {quote.name} @ {quote.current:.2f}")
    
    # 测试depth
    print("\n测试五档盘口:")
    depth = provider.depth('SH600519')
    if depth:
        print(f"  Bids: {len(depth.bids)}, Asks: {len(depth.asks)}")
        if depth.bids:
            print(f"  买一: {depth.bids[0]['price']} x {depth.bids[0]['volume']}")
    
    # 测试intraday
    print("\n测试分时数据:")
    intraday = provider.intraday('SH600519')
    if intraday:
        print(f"  获取到 {len(intraday)} 条分时数据")
        if intraday:
            print(f"  最新: {intraday[-1].time} @ {intraday[-1].price}")
    
    # 测试kline
    print("\n测试K线数据:")
    klines = provider.kline('SH600519', period='day', count=5)
    if klines:
        print(f"  获取到 {len(klines)} 条K线")
        for k in klines[-3:]:
            print(f"  {k.date}: 开{k.open} 收{k.close} 高{k.high} 低{k.low}")
    
    # 测试batch_quote（批量查询节省API调用）
    print("\n测试批量查询(节省API调用):")
    symbols = ['SH600519', 'SZ000001', 'SH600036']
    batch_results = provider.batch_quote(symbols)
    print(f"  批量查询 {len(symbols)} 只股票，只需1次API调用")
    for q in batch_results:
        print(f"  {q.symbol}: {q.name} @ {q.current:.2f}")
    
    print(f"\n总请求次数: {provider._request_count}")
    print("\n✓ TencentProvider test completed!")
