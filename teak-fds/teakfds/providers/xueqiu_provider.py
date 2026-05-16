#!/usr/bin/env python3
"""
XueqiuProvider - 雪球数据Provider
封装雪球API，提供A股/港股/美股实时行情和K线

完整功能列表（与原xueqiu-data skill保持一致）:
- 个股实时行情 (quote)
- 分时数据 (minute)
- K线数据 (kline)
- 盘口数据 (depth/pankou)
- 资金流向 (capital_flow, capital_history/money_flow)
- 组合调仓历史 (cube_rebalancing)
- 组合/股票批量报价 (cube_quote)
- 组合净值变化 (cube_nav)
- 自选股列表 (watchlist_stocks)
- 自选组合列表 (watchlist_cubes)
- 大盘指数行情 (index_quotes)
- 机构评级报告 (institution_report)
"""

import sys
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass

# 添加路径
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from teakfds.providers.base_provider import RealtimeProvider, ProviderCapabilities, ProviderStatus
from teakfds.datasource_log import log_info, log_warn, log_error
from teakfds.models import (
    QuoteData, DepthData, KlineData,
    normalize_symbol, detect_market
)

# 雪球客户端（包内路径）
try:
    from teakfds.xueqiu_client import XueqiuClient, CookieExpiredError, XueqiuRequestError
    _XUEQIU_AVAILABLE = True
except ImportError:
    _XUEQIU_AVAILABLE = False
    XueqiuClient = None


class XueqiuProvider(RealtimeProvider):
    """
    雪球数据Provider - 完整功能版
    
    特点:
    - 支持A股/港股/美股
    - 备用数据源
    - 支持实时行情和K线
    - 支持组合数据
    - 支持自选股同步
    """
    
    name = "xueqiu"
    display_name = "雪球"
    priority = 50  # 中等优先级
    
    capabilities = ProviderCapabilities(
        supports_quote=True,
        supports_depth=True,
        supports_kline=True,
        markets=['a_share', 'hk', 'us'],
        kline_periods=['day', 'week', 'month']
    )
    
    def __init__(self):
        super().__init__()
        self.client = None
        self._init_client()
    
    def _init_client(self):
        """初始化雪球客户端"""
        if not _XUEQIU_AVAILABLE:
            log_warn("✗ xueqiu_client not available, XueqiuProvider disabled")
            return
        
        try:
            self.client = XueqiuClient.create()
            self._available = True
            log_info("✓ XueqiuProvider initialized")
        except Exception as e:
            log_error(f"✗ XueqiuProvider init failed: {e}")
            self._available = False
    
    def is_available(self) -> bool:
        return self._available and self.client is not None
    
    def get_status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            available=self.is_available(),
            last_success=datetime.now().isoformat() if self.is_available() else None
        )
    
    def _to_xueqiu_symbol(self, symbol: str, is_index: bool = False) -> str:
        """转换为雪球代码格式

        注意：不同API需要不同格式
        - quote/minute: 支持小写 sh600519
        - kline/pankou: 需要大写 SH600519

        Args:
            symbol: 原始股票/指数代码
            is_index: 是否为指数代码（显式指定）。若为 True，000xxx → SH，399xxx → SZ。
                      若为 False（默认），使用自动判断：已知指数代码（000300等）自动识别。
        """
        market = detect_market(symbol)

        # 统一使用大写格式 (雪球API兼容性最好)
        symbol = symbol.upper().strip()

        if market == 'a_share':
            # 转换为大写格式 SH600519
            if symbol.startswith(('SH', 'SZ')):
                return symbol
            elif '.' in symbol:
                parts = symbol.split('.')
                return f"{parts[1]}{parts[0]}"

            # 已知上交所指数代码（无股票冲突的）
            SH_INDEX_CODES = {'000300', '000016', '000905', '000852', '000688', '000903', '000819'}
            # 已知深交所指数代码
            SZ_INDEX_CODES = {'399001', '399006', '399673', '399102'}

            if len(symbol) == 6 and symbol.isdigit():
                # 显式指定为指数
                if is_index:
                    if symbol.startswith('399'):
                        return f"SZ{symbol}"
                    return f"SH{symbol}"

                # 自动检测：已知指数代码
                if symbol in SH_INDEX_CODES:
                    return f"SH{symbol}"
                if symbol in SZ_INDEX_CODES:
                    return f"SZ{symbol}"

                # 股票代码：6/5/9 开头为沪市
                if symbol.startswith(('6', '5', '9')):
                    return f"SH{symbol}"
                else:
                    return f"SZ{symbol}"
            return symbol

        elif market == 'hk':
            # 港股使用 00700 格式 (去掉前缀和点)
            return symbol.replace('HK', '').replace('.HK', '').replace('.', '').strip()

        else:
            # 美股直接用代码
            return symbol
    
    # ========== 实时行情 ==========
    
    def quote(self, symbol: str) -> Optional[QuoteData]:
        """获取实时行情"""
        if not self.is_available():
            return None
        
        try:
            xq_symbol = self._to_xueqiu_symbol(symbol)
            result = self.client.quote(xq_symbol)
            
            if not result or 'data' not in result or not result['data']:
                return None
            
            q = result['data'].get('quote', {})
            if not q:
                return None
            
            market = detect_market(symbol)
            
            return QuoteData(
                symbol=normalize_symbol(symbol, 'standard'),
                name=q.get('name', ''),
                current=float(q.get('current', 0)),
                open=float(q.get('open', 0)),
                high=float(q.get('high', 0)),
                low=float(q.get('low', 0)),
                close=float(q.get('last_close', q.get('open', 0))),
                volume=int(q.get('volume', 0)),
                amount=float(q.get('amount', 0)),
                percent=float(q.get('percent', 0)),
                timestamp=datetime.now().isoformat(),
                source=self.name,
                currency='HKD' if market == 'hk' else 'USD' if market == 'us' else 'CNY'
            )
            
        except CookieExpiredError as e:
            print(f"XueqiuProvider cookie expired: {e}")
            self._available = False
            return None
        except Exception as e:
            log_error(f"XueqiuProvider.quote error for {symbol}: {e}")
            return None
    
    # ========== 分时数据 ==========
    
    def minute(self, symbol: str, period: str = '1d') -> Optional[Dict[str, Any]]:
        """获取分时数据
        
        Args:
            symbol: 股票代码
            period: 分时周期 (1d=当日, 5d=5日)
        
        Returns:
            雪球API原始返回数据
        """
        if not self.is_available():
            return None
        
        try:
            xq_symbol = self._to_xueqiu_symbol(symbol)
            return self.client.minute(xq_symbol, period=period)
        except Exception as e:
            log_error(f"XueqiuProvider.minute error for {symbol}: {e}")
            return None
    
    # ========== 盘口数据 ==========
    
    def depth(self, symbol: str) -> Optional[DepthData]:
        """获取盘口数据 (pankou)"""
        if not self.is_available():
            return None
        
        try:
            xq_symbol = self._to_xueqiu_symbol(symbol)
            result = self.client.pankou(xq_symbol)
            
            if not result or 'data' not in result or not result['data']:
                return None
            
            d = result['data']
            
            # 雪球盘口字段名: bp1-10 (买价), bc1-10 (买量), sp1-10 (卖价), sc1-10 (卖量)
            return DepthData(
                symbol=normalize_symbol(symbol, 'standard'),
                timestamp=datetime.now().isoformat(),
                source=self.name,
                bid1=float(d.get('bp1') or 0),
                bid_vol1=int(d.get('bc1') or 0),
                bid2=float(d.get('bp2') or 0),
                bid_vol2=int(d.get('bc2') or 0),
                bid3=float(d.get('bp3') or 0),
                bid_vol3=int(d.get('bc3') or 0),
                bid4=float(d.get('bp4') or 0),
                bid_vol4=int(d.get('bc4') or 0),
                bid5=float(d.get('bp5') or 0),
                bid_vol5=int(d.get('bc5') or 0),
                ask1=float(d.get('sp1') or 0),
                ask_vol1=int(d.get('sc1') or 0),
                ask2=float(d.get('sp2') or 0),
                ask_vol2=int(d.get('sc2') or 0),
                ask3=float(d.get('sp3') or 0),
                ask_vol3=int(d.get('sc3') or 0),
                ask4=float(d.get('sp4') or 0),
                ask_vol4=int(d.get('sc4') or 0),
                ask5=float(d.get('sp5') or 0),
                ask_vol5=int(d.get('sc5') or 0),
            )
            
        except Exception as e:
            log_error(f"XueqiuProvider.depth error for {symbol}: {e}")
            return None
    
    def pankou(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取盘口数据 (原始API返回)"""
        if not self.is_available():
            return None
        
        try:
            xq_symbol = self._to_xueqiu_symbol(symbol)
            return self.client.pankou(xq_symbol)
        except Exception as e:
            log_error(f"XueqiuProvider.pankou error for {symbol}: {e}")
            return None
    
    # ========== K线数据 ==========
    
    def kline(self, 
              symbol: str, 
              period: str = 'day',
              count: int = 30,
              start_date: str = None,
              end_date: str = None) -> Optional[List[KlineData]]:
        """获取K线数据"""
        if not self.is_available():
            return None
        
        try:
            xq_symbol = self._to_xueqiu_symbol(symbol)
            
            # 雪球 kline 接口仅稳定支持 day/week/month/quarter/year。
            # 分钟级 K 线请改用 minute_kline()。
            period_map = {
                'day': 'day',
                'week': 'week',
                'month': 'month',
                'quarter': 'quarter',
                'year': 'year',
            }

            if period not in period_map:
                log_warn(f"XueqiuProvider.kline: unsupported period {period}, use minute_kline for minute data")
                return None

            xq_period = period_map[period]
            
            result = self.client.kline(
                symbol=xq_symbol,
                period=xq_period,
                count=count
            )
            
            if not result or 'data' not in result:
                return None
            
            items = result['data'].get('item', [])
            if not items:
                return None
            
            results = []
            for item in items:
                # item格式: [timestamp, volume, open, high, low, close, percent, ...]
                if len(item) >= 6:
                    timestamp = item[0]
                    date_str = datetime.fromtimestamp(timestamp / 1000).strftime('%Y-%m-%d')
                    
                    results.append(KlineData(
                        date=date_str,
                        open=float(item[2]),
                        high=float(item[3]),
                        low=float(item[4]),
                        close=float(item[5]),
                        volume=int(item[1]),
                        amount=0  # 雪球K线不返回成交额
                    ))
            
            return results[-count:] if len(results) > count else results
            
        except Exception as e:
            log_error(f"XueqiuProvider.kline error for {symbol}: {e}")
            return None
    
    # ========== 资金流向 ==========
    
    def capital_flow(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取当日分钟级资金流向数据"""
        if not self.is_available():
            return None
        
        try:
            xq_symbol = self._to_xueqiu_symbol(symbol)
            return self.client.capital_flow(xq_symbol)
        except Exception as e:
            log_error(f"XueqiuProvider.capital_flow error for {symbol}: {e}")
            return None
    
    def capital_history(self, symbol: str, days: int = 30) -> Optional[List[Dict[str, Any]]]:
        """获取日级历史资金流向数据"""
        if not self.is_available():
            return None
        
        try:
            xq_symbol = self._to_xueqiu_symbol(symbol)
            result = self.client.capital_history(xq_symbol)
            
            if not result or 'data' not in result:
                return None
            
            items = result['data'].get('items', [])
            
            results = []
            for item in items:
                # item格式: {timestamp, amount}
                if 'timestamp' in item and 'amount' in item:
                    results.append({
                        'date': datetime.fromtimestamp(item['timestamp'] / 1000).strftime('%Y-%m-%d'),
                        'net_inflow': float(item['amount'])
                    })
            
            return results[-days:] if len(results) > days else results
            
        except Exception as e:
            log_error(f"XueqiuProvider.capital_history error for {symbol}: {e}")
            return None
    
    def money_flow(self, symbol: str, days: int = 30) -> Optional[List[Dict[str, Any]]]:
        """获取资金流向 (别名，兼容旧接口)"""
        return self.capital_history(symbol, days)
    
    # ========== 组合 (Cube) API ==========
    
    def cube_rebalancing(self, cube_symbol: str, count: int = 20, page: int = 1) -> Optional[Dict[str, Any]]:
        """获取组合调仓历史
        
        Args:
            cube_symbol: 组合代码，如 ZH3404752
            count: 返回条数
            page: 页码
        """
        if not self.is_available():
            return None
        
        try:
            return self.client.cube_rebalancing(cube_symbol, count=count, page=page)
        except Exception as e:
            log_error(f"XueqiuProvider.cube_rebalancing error for {cube_symbol}: {e}")
            return None
    
    def cube_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取组合/股票批量报价详情
        
        Args:
            symbol: 组合或股票代码，支持批量如 "SH600519,SZ000001"
        """
        if not self.is_available():
            return None
        
        try:
            return self.client.cube_quote(symbol)
        except Exception as e:
            log_error(f"XueqiuProvider.cube_quote error for {symbol}: {e}")
            return None
    
    def cube_nav(self, cube_symbol: str, since_ms: Optional[int] = None, until_ms: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """获取组合净值变化
        
        Args:
            cube_symbol: 组合代码，如 ZH3404752
            since_ms: 开始时间戳（毫秒），默认90天前
            until_ms: 结束时间戳（毫秒），默认现在
        """
        if not self.is_available():
            return None
        
        try:
            return self.client.cube_nav(cube_symbol, since_ms=since_ms, until_ms=until_ms)
        except Exception as e:
            log_error(f"XueqiuProvider.cube_nav error for {cube_symbol}: {e}")
            return None
    
    # ========== 自选股 API ==========
    
    def watchlist_stocks(self, size: int = 1000) -> Optional[Dict[str, Any]]:
        """获取自选股列表"""
        if not self.is_available():
            return None
        
        try:
            return self.client.watchlist_stocks(size=size)
        except Exception as e:
            log_error(f"XueqiuProvider.watchlist_stocks error: {e}")
            return None
    
    def watchlist_cubes(self, size: int = 1000) -> Optional[Dict[str, Any]]:
        """获取自选组合列表"""
        if not self.is_available():
            return None
        
        try:
            return self.client.watchlist_cubes(size=size)
        except Exception as e:
            log_error(f"XueqiuProvider.watchlist_cubes error: {e}")
            return None
    
    # ========== 大盘指数 API ==========
    
    def index_quotes(self) -> Optional[Dict[str, Any]]:
        """获取首页大盘核心指数行情
        
        Returns:
            上证指数、深证成指、创业板指等指数行情
        """
        if not self.is_available():
            return None
        
        try:
            return self.client.index_quotes()
        except Exception as e:
            log_error(f"XueqiuProvider.index_quotes error: {e}")
            return None
    
    # ========== 研报 API ==========
    
    def institution_report(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取个股机构评级报告数据
        
        Args:
            symbol: 股票代码
        """
        if not self.is_available():
            return None
        
        try:
            xq_symbol = self._to_xueqiu_symbol(symbol)
            return self.client.institution_report(xq_symbol)
        except Exception as e:
            log_error(f"XueqiuProvider.institution_report error for {symbol}: {e}")
            return None


# 全局实例
xueqiu_provider: Optional[XueqiuProvider] = None


def get_xueqiu_provider() -> XueqiuProvider:
    """获取全局XueqiuProvider"""
    global xueqiu_provider
    if xueqiu_provider is None:
        xueqiu_provider = XueqiuProvider()
    return xueqiu_provider


if __name__ == '__main__':
    # 测试
    print("=" * 60)
    print("Testing XueqiuProvider - 完整功能测试")
    print("=" * 60)
    
    provider = XueqiuProvider()
    
    if provider.is_available():
        # 测试A股行情
        print("\n1. A-share quote:")
        quote = provider.quote('SH600519')
        if quote:
            print(f"   {quote.symbol}: {quote.name} @ {quote.current:.2f}")
        
        # 测试港股行情
        print("\n2. HK quote:")
        quote = provider.quote('00700.HK')
        if quote:
            print(f"   {quote.symbol}: {quote.name} @ {quote.current:.2f}")
        
        # 测试K线
        print("\n3. Kline:")
        klines = provider.kline('SH600519', period='day', count=3)
        if klines:
            print(f"   {len(klines)} klines retrieved")
        
        # 测试分时
        print("\n4. Minute data:")
        minute = provider.minute('SH600519')
        if minute:
            print(f"   Minute data retrieved")
        
        # 测试盘口
        print("\n5. Depth/Pankou:")
        depth = provider.depth('SH600519')
        if depth:
            print(f"   Bid1: {depth.bid1}, Ask1: {depth.ask1}")
        
        # 测试资金流向
        print("\n6. Capital flow:")
        flow = provider.capital_flow('SH600519')
        if flow:
            print(f"   Capital flow data retrieved")
        
        # 测试大盘指数
        print("\n7. Index quotes:")
        indices = provider.index_quotes()
        if indices:
            print(f"   Index data retrieved")
        
        print("\n" + "=" * 60)
        print("All tests passed!")
        print("=" * 60)
    else:
        print("✗ XueqiuProvider not available (check cookies)")
