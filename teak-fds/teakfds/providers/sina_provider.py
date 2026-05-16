#!/usr/bin/env python3
"""
SinaProvider - 新浪财经实时行情
P2级别 - A股/港股/美股备份源
"""

import requests
import re
import time
from typing import Optional, List
from datetime import datetime

import sys
from pathlib import Path

# 添加路径支持多种导入方式
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from teakfds.datasource_log import log_external_request

from teakfds.providers.base_provider import BaseProvider, ProviderCapabilities
from teakfds.models import QuoteData, DepthData, KlineData, ProviderStatus


class SinaProvider(BaseProvider):
    """新浪财经数据源Provider - P2级别备份源
    
    限流配置: ≤5次/秒
    """
    
    name = "sina"
    display_name = "新浪财经"
    priority = 80
    
    capabilities = ProviderCapabilities(
        supports_quote=True,
        # 注：sina 当前仅实现了 quote 和 A 股日/周/月 K 线；depth/intraday 暂未实现
        supports_depth=False,
        supports_intraday=False,
        supports_kline=True,
        markets=['a_share', 'hk', 'us'],
        kline_periods=['day', 'week', 'month']
    )
    
    QUOTE_URL = "https://hq.sinajs.cn/list="
    KLINE_URL = "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData"
    
    def __init__(self):
        super().__init__()
        self._last_request_time = 0
        self._min_interval = 0.2  # 5次/秒限制
    
    def _rate_limit(self):
        """限流控制"""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()

    def _logged_get(
        self,
        url: str,
        *,
        headers: dict,
        timeout: float,
        action: str = "http",
        symbol: Optional[str] = None,
        log_params: Optional[dict] = None,
    ):
        """带外呼日志的 GET。"""
        t0 = time.perf_counter()
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            elapsed = (time.perf_counter() - t0) * 1000
            final = str(resp.url)
            log_external_request(
                provider="sina",
                method="GET",
                url=final,
                action=action,
                symbol=symbol,
                success=resp.status_code == 200,
                status_code=resp.status_code,
                duration_ms=elapsed,
                message="ok" if resp.status_code == 200 else (resp.text[:200] if resp.text else ""),
                params=log_params,
                caller="SinaProvider._logged_get",
            )
            return resp
        except Exception as e:
            log_external_request(
                provider="sina",
                method="GET",
                url=url,
                action=action,
                symbol=symbol,
                success=False,
                duration_ms=(time.perf_counter() - t0) * 1000,
                message=str(e)[:800],
                params=log_params,
                caller="SinaProvider._logged_get",
            )
            raise

    def is_available(self) -> bool:
        try:
            resp = self._logged_get(
                f"{self.QUOTE_URL}sh600519",
                headers={'Referer': 'https://finance.sina.com.cn/'},
                timeout=3,
                action="is_available",
            )
            return resp.status_code == 200
        except Exception:
            return False
    
    def get_status(self) -> ProviderStatus:
        available = self.is_available()
        return ProviderStatus(
            name=self.name,
            available=available,
            last_success=datetime.now().isoformat() if available else None,
            avg_latency_ms=self._test_latency()
        )
    
    def _test_latency(self) -> float:
        start = time.time()
        try:
            self._logged_get(
                f"{self.QUOTE_URL}sh600519",
                headers={'Referer': 'https://finance.sina.com.cn/'},
                timeout=3,
                action="latency_probe",
            )
            return (time.time() - start) * 1000
        except Exception:
            return -1
    
    def _convert_symbol(self, symbol: str, is_index: bool = False) -> str:
        symbol = symbol.upper().strip()

        if symbol.startswith('SH'):
            return f"sh{symbol[2:]}"
        if symbol.startswith('SZ'):
            return f"sz{symbol[2:]}"
        if symbol.startswith('BJ'):
            return f"bj{symbol[2:]}"
        if symbol.endswith('.SH'):
            return f"sh{symbol[:-3]}"
        if symbol.endswith('.SZ'):
            return f"sz{symbol[:-3]}"

        if '.HK' in symbol or symbol.startswith('HK'):
            code = symbol.replace('.HK', '').replace('HK', '')
            return f"hk{code.zfill(5)}"

        # 已知上交所指数代码（无股票冲突的）
        SH_INDEX_CODES = {'000300', '000016', '000905', '000852', '000688', '000903', '000819'}
        # 已知深交所指数代码
        SZ_INDEX_CODES = {'399001', '399006', '399673', '399102'}

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

        return f"gb_{symbol.lower()}"
    
    def quote(self, symbol: str) -> Optional[QuoteData]:
        try:
            sina_symbol = self._convert_symbol(symbol)
            url = f"{self.QUOTE_URL}{sina_symbol}"
            
            resp = self._logged_get(
                url,
                headers={'Referer': 'https://finance.sina.com.cn/'},
                timeout=5,
                action="quote",
                symbol=symbol,
            )
            if resp.status_code != 200:
                return None
            
            text = resp.text.strip()
            if not text or '=' not in text:
                return None
            
            match = re.search(r'"(.*)"', text)
            if not match:
                return None
            
            data_str = match.group(1)
            if not data_str:
                return None
            
            parts = data_str.split(',')
            
            if sina_symbol.startswith(('sh', 'sz', 'bj')):
                if len(parts) < 33:
                    return None
                
                name = parts[0]
                open_price = float(parts[1]) if parts[1] else 0
                yesterday_close = float(parts[2]) if parts[2] else 0
                current = float(parts[3]) if parts[3] else 0
                high = float(parts[4]) if parts[4] else 0
                low = float(parts[5]) if parts[5] else 0
                volume = int(float(parts[8])) if parts[8] else 0
                amount = float(parts[9]) if parts[9] else 0
                
            elif sina_symbol.startswith('hk'):
                if len(parts) < 19:
                    return None
                
                name = parts[1]
                open_price = float(parts[2]) if parts[2] else 0
                yesterday_close = float(parts[3]) if parts[3] else 0
                high = float(parts[4]) if parts[4] else 0
                low = float(parts[5]) if parts[5] else 0
                current = float(parts[6]) if parts[6] else 0
                volume = int(float(parts[12])) if parts[12] else 0
                amount = float(parts[11]) if parts[11] else 0
                
            elif sina_symbol.startswith('gb_'):
                if len(parts) < 6:
                    return None
                
                name = parts[0]
                current = float(parts[1]) if parts[1] else 0
                open_price = float(parts[5]) if len(parts) > 5 and parts[5] else 0
                high = float(parts[6]) if len(parts) > 6 and parts[6] else 0
                low = float(parts[7]) if len(parts) > 7 and parts[7] else 0
                volume = int(float(parts[10])) if len(parts) > 10 and parts[10] else 0
                amount = 0
                yesterday_close = open_price
                
            else:
                return None
            
            percent = 0
            if yesterday_close > 0:
                percent = (current - yesterday_close) / yesterday_close * 100
            
            return QuoteData(
                symbol=symbol,
                name=name,
                current=current,
                open=open_price,
                high=high,
                low=low,
                close=yesterday_close,
                volume=volume,
                amount=amount,
                percent=percent,
                timestamp=datetime.now().isoformat(),
                source=self.name
            )
            
        except Exception as e:
            print(f"SinaProvider.quote error: {e}")
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
            period: 周期 ('day', 'week', 'month')
            count: 获取条数
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)
        
        Returns:
            KlineData列表或None
        """
        self._rate_limit()
        
        try:
            sina_symbol = self._convert_symbol(symbol)
            
            # 只支持A股K线
            if not sina_symbol.startswith(('sh', 'sz', 'bj')):
                print("Sina kline only supports A-share")
                return None
            
            # 周期映射
            period_map = {
                'day': 'day',
                'week': 'week',
                'month': 'month'
            }
            
            if period not in period_map:
                print(f"Unsupported period: {period}")
                return None
            
            # 构建请求参数
            params = {
                'symbol': sina_symbol,
                'type': period_map[period],
                'scale': '240' if period == 'day' else '1',
                'datalen': str(count)
            }
            
            t0 = time.perf_counter()
            try:
                resp = requests.get(
                    self.KLINE_URL,
                    params=params,
                    headers={'Referer': 'https://finance.sina.com.cn/'},
                    timeout=10
                )
            except Exception as e:
                log_external_request(
                    provider="sina",
                    method="GET",
                    url=self.KLINE_URL,
                    action="kline",
                    symbol=symbol,
                    success=False,
                    duration_ms=(time.perf_counter() - t0) * 1000,
                    message=str(e)[:800],
                    params=params,
                    caller="SinaProvider.kline",
                )
                raise
            log_external_request(
                provider="sina",
                method="GET",
                url=str(resp.url),
                action="kline",
                symbol=symbol,
                success=resp.status_code == 200,
                status_code=resp.status_code,
                duration_ms=(time.perf_counter() - t0) * 1000,
                message="ok" if resp.status_code == 200 else (resp.text[:200] if resp.text else ""),
                params=params,
                caller="SinaProvider.kline",
            )
            
            if resp.status_code != 200:
                return None
            
            data = resp.json()
            if not data:
                return None
            
            # 解析K线数据
            klines = []
            for item in data:
                try:
                    # 新浪K线格式可能有变化，尝试多种解析方式
                    if isinstance(item, dict):
                        day = item.get('day', '')
                        open_p = float(item.get('open', 0))
                        high = float(item.get('high', 0))
                        low = float(item.get('low', 0))
                        close = float(item.get('close', 0))
                        volume = int(float(item.get('volume', 0)))
                    elif isinstance(item, (list, tuple)) and len(item) >= 6:
                        day = str(item[0])
                        open_p = float(item[1])
                        high = float(item[2])
                        low = float(item[3])
                        close = float(item[4])
                        volume = int(float(item[5]))
                    else:
                        continue
                    
                    klines.append(KlineData(
                        date=day,
                        open=open_p,
                        high=high,
                        low=low,
                        close=close,
                        volume=volume,
                        amount=0,
                    ))
                except Exception:
                    continue
            
            return klines
            
        except Exception as e:
            print(f"SinaProvider.kline error: {e}")
            return None


_sina_provider: Optional[SinaProvider] = None

def get_sina_provider() -> SinaProvider:
    global _sina_provider
    if _sina_provider is None:
        _sina_provider = SinaProvider()
    return _sina_provider
