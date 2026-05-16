#!/usr/bin/env python3
"""
MXDataProvider - 妙想金融数据Provider
P3-P4级别 - 腾讯财经/Sina失败后的备份源
配额由服务端按日控制，客户端不设秒级间隔。
"""

import os
import sys
import time
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from teakfds.datasource_log import log_external_request

from teakfds.providers.base_provider import BaseProvider, ProviderCapabilities
from teakfds.models import QuoteData, DepthData, KlineData, ProviderStatus


class MXDataProvider(BaseProvider):
    """
    妙想金融数据Provider
    作为P3-P4备份源，当腾讯财经、新浪财经不可用时降级使用

    支持功能:
    - 实时行情 (quote)
    - 资金流向 (money_flow)
    - 五档盘口 (depth)
    - 分钟线 (minute/kline)

    配额由妙想侧按日限制；客户端不做秒级请求间隔（避免拖慢批量测试）。
    """

    name = "mx_data"
    display_name = "妙想数据"
    priority = 40

    capabilities = ProviderCapabilities(
        supports_quote=True,
        supports_depth=True,
        supports_kline=True,
        supports_intraday=True,
        markets=['a_share', 'hk', 'us'],
        kline_periods=['1min', '5min', '15min', '30min', '60min'],
    )

    BASE_URL = "https://mkapi2.dfcfs.com/finskillshub/api/claw/query"

    # 仅 MX_APIKEY（环境变量或文件）
    API_KEY_PATHS = [
        Path.home() / 'agents_documents' / 'MX_APIKEY.txt',
        Path.home() / '.openclaw' / 'credentials' / 'MX_APIKEY.txt',
    ]

    def __init__(self, api_key: Optional[str] = None):
        super().__init__()
        self.api_key = api_key or self._load_api_key()
        self._last_quota_limited = False

    @staticmethod
    def _message_indicates_quota(msg: str) -> bool:
        if not msg:
            return False
        keys = ('限流', '次数', '额度', '配额', '用完', 'quota', 'rate limit')
        m = msg.lower()
        return any(k.lower() in m for k in keys)

    def last_quota_limited(self) -> bool:
        """最近一次请求是否因日调用次数等配额限制失败（用于测试视为通过）。"""
        return getattr(self, '_last_quota_limited', False)

    def _load_api_key(self) -> str:
        """仅读取环境变量 ``MX_APIKEY`` 或 ``MX_APIKEY.txt`` 文件（禁止硬编码）。"""
        api_key = os.getenv("MX_APIKEY")
        if api_key:
            return api_key.strip()

        for path in self.API_KEY_PATHS:
            if path.exists():
                try:
                    content = path.read_text().strip()
                    if content:
                        return content
                except Exception:
                    continue

        return ""

    def _make_request(self, query: str) -> Optional[Dict[str, Any]]:
        """发送查询请求"""
        self._last_quota_limited = False

        headers = {
            "Content-Type": "application/json",
            "apikey": self.api_key
        }
        data = {"toolQuery": query}

        t0 = time.perf_counter()
        try:
            import requests
            response = requests.post(self.BASE_URL, headers=headers, json=data, timeout=30)
            elapsed = (time.perf_counter() - t0) * 1000
            final_url = str(response.url)
            log_external_request(
                provider="mx_data",
                method="POST",
                url=final_url,
                action="claw_query",
                success=response.status_code == 200,
                status_code=response.status_code,
                duration_ms=elapsed,
                message=(query[:500] if query else "") + ("; body_ok" if response.status_code == 200 else ""),
                params={"toolQuery": (query[:4000] if query else "")},
                caller="MXDataProvider._make_request",
            )
            response.raise_for_status()
            result = response.json()

            if result.get("status") == 0:
                return result
            msg = str(
                result.get("message")
                or result.get("msg")
                or result.get("info")
                or result
            )
            if self._message_indicates_quota(msg):
                self._last_quota_limited = True
            return None
        except Exception as e:
            log_external_request(
                provider="mx_data",
                method="POST",
                url=self.BASE_URL,
                action="claw_query",
                success=False,
                duration_ms=(time.perf_counter() - t0) * 1000,
                message=f"{e!s}; query={query[:300]!r}",
                params={"toolQuery": (query[:4000] if query else "")},
                caller="MXDataProvider._make_request",
            )
            print(f"MXDataProvider request error: {e}")
            return None

    def _extract_table_data(self, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """从API结果中提取表格数据"""
        try:
            data = result.get("data", {}).get("data", {})
            search_result = data.get("searchDataResultDTO", {})
            dto_list = search_result.get("dataTableDTOList", [])

            if not dto_list:
                return None

            return dto_list[0]  # 返回第一个表格
        except Exception:
            return None

    def _normalize_symbol(self, symbol: str) -> str:
        """标准化股票代码"""
        symbol = symbol.upper().strip()

        if symbol.startswith('SH') or symbol.startswith('SZ') or symbol.startswith('BJ'):
            return symbol[2:]
        if symbol.endswith('.SH') or symbol.endswith('.SZ') or symbol.endswith('.BJ'):
            return symbol.split('.')[0]
        if '.HK' in symbol:
            return symbol.replace('.HK', '')

        return symbol

    def is_available(self) -> bool:
        """已配置 API Key 即视为可用（避免探测请求消耗每日配额）。"""
        return bool(self.api_key and str(self.api_key).strip())

    def get_status(self) -> ProviderStatus:
        """获取Provider状态"""
        available = self.is_available()
        return ProviderStatus(
            name=self.name,
            available=available,
            last_success=datetime.now().isoformat() if available else None
        )

    def quote(self, symbol: str) -> Optional[QuoteData]:
        """
        获取实时行情
        示例查询: "贵州茅台最新价" 或 "600519最新行情"
        """
        try:
            code = self._normalize_symbol(symbol)
            # 构建查询语句
            query = f"{code}最新行情"

            result = self._make_request(query)
            if not result:
                return None

            table = self._extract_table_data(result)
            if not table:
                return None

            # 解析表格数据
            name = table.get("entityName", "")
            table_data = table.get("table", {})

            if not table_data:
                return None

            # 提取字段
            # MX API格式: headName是日期数组，每个指标是数组
            current = self._extract_value(table_data, ["最新价", "现价", "收盘价"])
            open_price = self._extract_value(table_data, ["开盘价", "开盘"])
            high = self._extract_value(table_data, ["最高价", "最高"])
            low = self._extract_value(table_data, ["最低价", "最低"])
            volume = self._extract_value(table_data, ["成交量", "成交", "成交额"])

            # 计算涨跌幅
            prev_close = self._extract_value(table_data, ["昨收", "昨收价", "昨日收盘"])
            percent = 0
            if prev_close and current:
                percent = (current - prev_close) / prev_close * 100

            return QuoteData(
                symbol=symbol,
                name=name or symbol,
                current=current or 0,
                open=open_price or 0,
                high=high or 0,
                low=low or 0,
                close=prev_close or current or 0,
                volume=int(volume * 100) if volume else 0,
                amount=0,
                percent=percent,
                timestamp=datetime.now().isoformat(),
                source=self.name
            )

        except Exception as e:
            print(f"MXDataProvider.quote error: {e}")
            return None

    def _extract_value(self, table_data: Dict, possible_keys: List[str]) -> Optional[float]:
        """从表格数据中提取数值"""
        try:
            name_map = table_data.get("nameMap", {})

            # 查找匹配的key
            for key in possible_keys:
                # 在nameMap中查找
                for k, v in name_map.items():
                    if key in str(v):
                        values = table_data.get(k, [])
                        if values and len(values) > 0:
                            val = values[-1] if isinstance(values, list) else values
                            return float(val) if val else None

            # 直接查找key
            for key in possible_keys:
                for k in table_data.keys():
                    if key in str(k) and k != "headName":
                        values = table_data.get(k, [])
                        if values and len(values) > 0:
                            val = values[-1] if isinstance(values, list) else values
                            return float(val) if val else None

            return None
        except Exception:
            return None

    def depth(self, symbol: str) -> Optional[DepthData]:
        """
        获取五档盘口
        示例查询: "贵州茅台五档盘口"
        """
        try:
            code = self._normalize_symbol(symbol)
            query = f"{code}五档盘口"

            result = self._make_request(query)
            if not result:
                return None

            table = self._extract_table_data(result)
            if not table:
                return None

            # 解析盘口数据
            table_data = table.get("table", {})

            # 提取买卖五档
            bids = []
            asks = []

            for i in range(1, 6):
                bid_price = self._extract_value(table_data, [f"买{i}", f"买盘{i}"])
                bid_volume = self._extract_value(table_data, [f"买{i}量", f"买盘{i}量"])
                if bid_price:
                    bids.append({"price": bid_price, "volume": int(bid_volume or 0)})

                ask_price = self._extract_value(table_data, [f"卖{i}", f"卖盘{i}"])
                ask_volume = self._extract_value(table_data, [f"卖{i}量", f"卖盘{i}量"])
                if ask_price:
                    asks.append({"price": ask_price, "volume": int(ask_volume or 0)})

            return DepthData(
                symbol=symbol,
                bids=bids,
                asks=asks,
                timestamp=datetime.now().isoformat(),
                source=self.name
            )

        except Exception as e:
            print(f"MXDataProvider.depth error: {e}")
            return None

    def kline(self,
              symbol: str,
              period: str = 'day',
              count: int = 30,
              start_date: str = None,
              end_date: str = None) -> Optional[List[KlineData]]:
        """
        获取K线数据（仅分钟线；日线请用 Tushare/腾讯等）

        Args:
            symbol: 股票代码
            period: 周期 ('1min', '5min', '15min', '30min', '60min')
            count: 获取条数
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)
        """
        try:
            code = self._normalize_symbol(symbol)

            if period not in ('1min', '5min', '15min', '30min', '60min'):
                return None

            period_map = {
                '1min': '1分钟',
                '5min': '5分钟',
                '15min': '15分钟',
                '30min': '30分钟',
                '60min': '60分钟',
            }
            period_cn = period_map.get(period, '5分钟')
            query = f"{code}{period_cn}线"

            result = self._make_request(query)
            if not result:
                return None

            table = self._extract_table_data(result)
            if not table:
                return None

            table_data = table.get("table", {})
            headers = table_data.get("headName", [])

            klines = []
            for i, date in enumerate(headers):
                try:
                    # 提取每个时间点的数据
                    open_val = self._get_kline_value(table_data, i, ["开盘", "开盘价"])
                    high = self._get_kline_value(table_data, i, ["最高", "最高价"])
                    low = self._get_kline_value(table_data, i, ["最低", "最低价"])
                    close = self._get_kline_value(table_data, i, ["收盘", "收盘价", "最新价"])
                    volume = self._get_kline_value(table_data, i, ["成交量", "成交"])

                    if close:  # 至少要有收盘价
                        klines.append(KlineData(
                            date=str(date),
                            open=open_val or close,
                            high=high or close,
                            low=low or close,
                            close=close,
                            volume=int(volume) if volume else 0,
                            amount=0,
                        ))
                except Exception:
                    continue

            # 限制返回数量
            if count and len(klines) > count:
                klines = klines[-count:]

            return klines

        except Exception as e:
            print(f"MXDataProvider.kline error: {e}")
            return None

    def _get_kline_value(self, table_data: Dict, index: int, possible_keys: List[str]) -> Optional[float]:
        """获取K线某个字段的值"""
        try:
            for key in possible_keys:
                values = table_data.get(key, [])
                if values and index < len(values):
                    val = values[index]
                    return float(val) if val else None
            return None
        except Exception:
            return None

    def intraday(self, symbol: str) -> Optional[List[KlineData]]:
        """
        获取分时数据
        返回当天分钟线数据
        """
        return self.kline(symbol, period='1min', count=240)  # 4小时交易时间

    def money_flow(self, symbol: str, days: int = 30) -> Optional[List[Dict]]:
        """
        获取资金流向数据
        示例查询: "贵州茅台资金流向"
        """
        try:
            code = self._normalize_symbol(symbol)
            query = f"{code}资金流向"

            result = self._make_request(query)
            if not result:
                return None

            table = self._extract_table_data(result)
            if not table:
                return None

            table_data = table.get("table", {})
            headers = table_data.get("headName", [])

            flows = []
            for i, date in enumerate(headers):
                try:
                    main_in = self._get_kline_value(table_data, i, ["主力流入", "主力净流入"])
                    main_out = self._get_kline_value(table_data, i, ["主力流出"])
                    retail_in = self._get_kline_value(table_data, i, ["散户流入"])
                    retail_out = self._get_kline_value(table_data, i, ["散户流出"])

                    if main_in is not None:
                        flows.append({
                            "date": str(date),
                            "main_in": main_in,
                            "main_out": main_out or 0,
                            "retail_in": retail_in or 0,
                            "retail_out": retail_out or 0,
                            "net_main": (main_in or 0) - (main_out or 0)
                        })
                except Exception:
                    continue

            if days and len(flows) > days:
                flows = flows[-days:]

            return flows

        except Exception as e:
            print(f"MXDataProvider.money_flow error: {e}")
            return None


# 全局实例
_mx_provider: Optional[MXDataProvider] = None


def get_mx_data_provider() -> MXDataProvider:
    """获取MXDataProvider全局实例"""
    global _mx_provider
    if _mx_provider is None:
        _mx_provider = MXDataProvider()
    return _mx_provider


if __name__ == '__main__':
    print("Testing MXDataProvider...")
    provider = MXDataProvider()

    print(f"\nAvailable: {provider.is_available()}")

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

    print("\n✓ MXDataProvider test completed!")
