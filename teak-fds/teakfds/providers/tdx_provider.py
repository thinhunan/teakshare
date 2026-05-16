#!/usr/bin/env python3
"""
TdxProvider - 通达信数据Provider
封装mootdx库，提供A股实时行情和分钟K线
"""

import sys
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass
from datetime import datetime

# 添加路径
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from teakfds.providers.base_provider import RealtimeProvider, ProviderCapabilities, ProviderStatus
from teakfds.models import (
    QuoteData, DepthData, KlineData, IntradayData,
    TickData, FinanceSnapshotData, XdxrData,
    normalize_symbol, detect_market
)
from teakfds.datasource_log import log_info, log_warn, log_error

# 尝试导入mootdx
try:
    from mootdx.quotes import Quotes
    from mootdx.consts import MARKET_SH, MARKET_SZ
    _MOOTDX_AVAILABLE = True
except ImportError:
    _MOOTDX_AVAILABLE = False
    Quotes = None
    MARKET_SH = 1
    MARKET_SZ = 0


class TdxProvider(RealtimeProvider):
    """
    通达信数据Provider
    
    特点:
    - A股实时行情主源
    - 毫秒级延迟
    - 支持分钟K线
    - 支持盘口数据
    """
    
    name = "tdx"
    display_name = "通达信"
    priority = 100  # 最高优先级
    
    capabilities = ProviderCapabilities(
        supports_quote=True,
        supports_depth=True,
        supports_intraday=True,
        supports_kline=True,
        supports_tick=True,
        supports_finance_snapshot=True,
        supports_f10=True,
        supports_xdxr=True,
        supports_money_flow=True,
        markets=['a_share'],
        kline_periods=['1min', '5min', '15min', '30min', '60min', 'day', 'week', 'month']
    )
    
    def __init__(self):
        super().__init__()
        self.client = None
        self._available = False
        # 不在 __init__ 中连接，改为延迟连接
    
    def _connect(self):
        """连接通达信服务器"""
        if self.client is not None:
            return  # 已连接
        
        if not _MOOTDX_AVAILABLE:
            log_warn("✗ mootdx not available, TdxProvider disabled")
            return
        
        try:
            self.client = Quotes.factory(
                market='std',
                multithread=True,
                heartbeat=True
            )
            self._available = True
            log_info("✓ TdxProvider connected")
        except Exception as e:
            log_error(f"✗ TdxProvider connection failed: {e}")
            self._available = False
    
    def _ensure_connected(self):
        """确保已连接（延迟连接）"""
        if self.client is None and not self._available:
            self._connect()
    
    def is_available(self) -> bool:
        # 延迟连接检查
        if self.client is None and not self._available:
            self._connect()
        return self._available and self.client is not None
    
    def get_status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            available=self.is_available(),
            last_success=datetime.now().isoformat() if self.is_available() else None
        )
    
    def _normalize_symbol(self, symbol: str, is_index: bool = False) -> tuple:
        """
        转换为通达信格式
        返回: (market, code)

        Args:
            symbol: 股票/指数代码
            is_index: 是否为指数代码（显式指定）。若为 True，000xxx → SH，399xxx → SZ。
                      若为 False（默认），使用自动判断：已知指数代码（000300等）自动识别。
        """
        symbol = symbol.upper().strip()

        if symbol.startswith('SH'):
            return MARKET_SH, symbol[2:]
        if symbol.startswith('SZ'):
            return MARKET_SZ, symbol[2:]
        if symbol.endswith('.SH'):
            return MARKET_SH, symbol[:-3]
        if symbol.endswith('.SZ'):
            return MARKET_SZ, symbol[:-3]

        # 已知上交所指数代码（无股票冲突的）
        # 注意：000001/000002/000003 与常见股票冲突，不放入自动检测集合
        SH_INDEX_CODES = {'000300', '000016', '000905', '000852', '000688', '000903', '000819'}
        # 已知深交所指数代码
        SZ_INDEX_CODES = {'399001', '399006', '399673', '399102'}

        # 根据开头判断
        if len(symbol) == 6 and symbol.isdigit():
            # 显式指定为指数
            if is_index:
                if symbol.startswith('399'):
                    return MARKET_SZ, symbol
                return MARKET_SH, symbol

            # 自动检测：已知指数代码
            if symbol in SH_INDEX_CODES:
                return MARKET_SH, symbol
            if symbol in SZ_INDEX_CODES:
                return MARKET_SZ, symbol

            # 股票代码：6/5/9 开头为沪市，其他为深市
            if symbol.startswith(('6', '5', '9')):
                return MARKET_SH, symbol
            else:
                return MARKET_SZ, symbol

        return MARKET_SZ, symbol
    
    # ========== 实时行情 ==========
    
    def quote(self, symbol: str) -> Optional[QuoteData]:
        """获取实时行情"""
        if not self.is_available():
            return None
        
        try:
            market, code = self._normalize_symbol(symbol)
            
            # 获取实时行情
            df = self.client.quotes(symbol=[code])
            
            if df is None or df.empty:
                return None
            
            row = df.iloc[0]
            
            # 构建标准代码
            std_symbol = f"SH{code}" if market == MARKET_SH else f"SZ{code}"
            
            # 价格单位转换
            price_div = 100.0
            
            current = float(row.get('price', 0)) / price_div
            open_price = float(row.get('open', 0)) / price_div
            high = float(row.get('high', 0)) / price_div
            low = float(row.get('low', 0)) / price_div
            prev_close = float(row.get('last_close', row.get('open', 0))) / price_div
            
            # 计算涨跌幅
            percent = (current - prev_close) / prev_close * 100 if prev_close > 0 else 0
            
            return QuoteData(
                symbol=std_symbol,
                name=row.get('name', ''),
                current=current,
                open=open_price,
                high=high,
                low=low,
                close=prev_close,
                volume=int(row.get('volume', 0)),
                amount=float(row.get('amount', 0)),
                percent=percent,
                timestamp=row.get('datetime', datetime.now().isoformat()),
                source=self.name,
                bid1=float(row.get('bid1', 0)) / price_div if 'bid1' in row else None,
                ask1=float(row.get('ask1', 0)) / price_div if 'ask1' in row else None,
            )
            
        except Exception as e:
            log_error(f"TdxProvider.quote error for {symbol}: {e}")
            return None
    
    def batch_quote(self, symbols: List[str]) -> List[QuoteData]:
        """批量获取实时行情"""
        if not self.is_available():
            return []
        
        results = []
        
        try:
            # 转换所有代码
            code_list = []
            symbol_map = {}
            
            for symbol in symbols:
                market, code = self._normalize_symbol(symbol)
                code_list.append(code)
                symbol_map[code] = (symbol, market)
            
            # 批量获取
            df = self.client.quotes(symbol=code_list)
            
            if df is None or df.empty:
                return []
            
            price_div = 100.0
            
            for _, row in df.iterrows():
                code = str(row.get('code', ''))
                if code not in symbol_map:
                    continue
                
                orig_symbol, market = symbol_map[code]
                std_symbol = f"SH{code}" if market == MARKET_SH else f"SZ{code}"
                
                current = float(row.get('price', 0)) / price_div
                prev_close = float(row.get('last_close', row.get('open', 0))) / price_div
                percent = (current - prev_close) / prev_close * 100 if prev_close > 0 else 0
                
                results.append(QuoteData(
                    symbol=std_symbol,
                    name=row.get('name', ''),
                    current=current,
                    open=float(row.get('open', 0)) / price_div,
                    high=float(row.get('high', 0)) / price_div,
                    low=float(row.get('low', 0)) / price_div,
                    close=prev_close,
                    volume=int(row.get('volume', 0)),
                    amount=float(row.get('amount', 0)),
                    percent=percent,
                    timestamp=row.get('datetime', ''),
                    source=self.name
                ))
                
        except Exception as e:
            log_error(f"TdxProvider.batch_quote error: {e}")
        
        return results
    
    # ========== 盘口数据 ==========
    
    def depth(self, symbol: str) -> Optional[DepthData]:
        """获取盘口数据"""
        if not self.is_available():
            return None
        
        try:
            market, code = self._normalize_symbol(symbol)
            
            # 获取买卖盘
            df = self.client.quotes(symbol=[code])
            
            if df is None or df.empty:
                return None
            
            row = df.iloc[0]
            price_div = 100.0
            
            std_symbol = f"SH{code}" if market == MARKET_SH else f"SZ{code}"
            
            return DepthData(
                symbol=std_symbol,
                timestamp=datetime.now().isoformat(),
                source=self.name,
                bid1=float(row.get('bid1', 0)) / price_div,
                bid_vol1=int(row.get('bid_vol1', 0)),
                bid2=float(row.get('bid2', 0)) / price_div,
                bid_vol2=int(row.get('bid_vol2', 0)),
                bid3=float(row.get('bid3', 0)) / price_div,
                bid_vol3=int(row.get('bid_vol3', 0)),
                bid4=float(row.get('bid4', 0)) / price_div,
                bid_vol4=int(row.get('bid_vol4', 0)),
                bid5=float(row.get('bid5', 0)) / price_div,
                bid_vol5=int(row.get('bid_vol5', 0)),
                ask1=float(row.get('ask1', 0)) / price_div,
                ask_vol1=int(row.get('ask_vol1', 0)),
                ask2=float(row.get('ask2', 0)) / price_div,
                ask_vol2=int(row.get('ask_vol2', 0)),
                ask3=float(row.get('ask3', 0)) / price_div,
                ask_vol3=int(row.get('ask_vol3', 0)),
                ask4=float(row.get('ask4', 0)) / price_div,
                ask_vol4=int(row.get('ask_vol4', 0)),
                ask5=float(row.get('ask5', 0)) / price_div,
                ask_vol5=int(row.get('ask_vol5', 0)),
            )
            
        except Exception as e:
            log_error(f"TdxProvider.depth error for {symbol}: {e}")
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
            market, code = self._normalize_symbol(symbol)
            
            # 通达信周期映射
            category_map = {
                '1min': 8,
                '5min': 0,
                '15min': 1,
                '30min': 2,
                '60min': 3,
                'day': 9,
                'week': 5,
                'month': 6,
            }
            
            category = category_map.get(period, 9)
            
            # 获取K线
            df = self.client.bars(
                symbol=code,
                frequency=category,
                offset=0,
                count=count
            )
            
            if df is None or df.empty:
                return None
            
            results = []
            price_div = 100.0
            
            for _, row in df.iterrows():
                results.append(KlineData(
                    date=str(row.get('datetime', ''))[:10],
                    open=float(row.get('open', 0)) / price_div,
                    high=float(row.get('high', 0)) / price_div,
                    low=float(row.get('low', 0)) / price_div,
                    close=float(row.get('close', 0)) / price_div,
                    volume=int(row.get('volume', 0)),
                    amount=float(row.get('amount', 0))
                ))
            
            # 按日期排序 (从旧到新)
            results.reverse()
            return results[:count]
            
        except Exception as e:
            log_error(f"TdxProvider.kline error for {symbol}: {e}")
            return None
    
    # ========== 分时数据 ==========
    
    def intraday(self, symbol: str) -> Optional[List[IntradayData]]:
        """获取分时数据"""
        if not self.is_available():
            return None
        
        try:
            market, code = self._normalize_symbol(symbol)
            
            # 获取分时数据
            df = self.client.minute_bars(
                symbol=code,
                offset=0
            )
            
            if df is None or df.empty:
                return None
            
            results = []
            price_div = 100.0
            
            for _, row in df.iterrows():
                results.append(IntradayData(
                    time=str(row.get('datetime', ''))[11:16],
                    price=float(row.get('close', 0)) / price_div,
                    volume=int(row.get('volume', 0)),
                    amount=float(row.get('amount', 0)),
                    avg_price=float(row.get('price', row.get('close', 0))) / price_div
                ))
            
            return results
            
        except Exception as e:
            log_error(f"TdxProvider.intraday error for {symbol}: {e}")
            return None
    
    def close(self):
        """关闭连接"""
        if self.client:
            try:
                self.client.close()
            except:
                pass
            self.client = None

    # ========== 逐笔成交 ==========

    def transaction(self, symbol: str, start: int = 0, count: int = 800) -> Optional[List[TickData]]:
        """获取逐笔成交 (mootdx client.transactions)

        Args:
            symbol: 股票代码
            start: 起始位置
            count: 数量 (max 800 per call)
        Returns:
            TickData list or None
        """
        if not self.is_available():
            return None
        try:
            market, code = self._normalize_symbol(symbol)
            df = self.client.transactions(symbol=code, start=start, count=count)

            if df is None or df.empty:
                return None

            price_div = 100.0
            results = []
            for _, row in df.iterrows():
                # mootdx transactions 返回: time/price/vol/num/buyorsell
                direction = ''
                buy_or_sell = row.get('buyorsell', 0)
                if buy_or_sell == 0:
                    direction = '买盘'
                elif buy_or_sell == 1:
                    direction = '卖盘'
                else:
                    direction = '中性'

                results.append(TickData(
                    time=str(row.get('time', '')),
                    price=float(row.get('price', 0)) / price_div,
                    volume=int(row.get('vol', 0)),
                    amount=float(row.get('price', 0)) / price_div * int(row.get('vol', 0)),
                    direction=direction,
                ))
            return results
        except Exception as e:
            log_error(f"TdxProvider.transaction error for {symbol}: {e}")
            return None

    def transaction_history(self, symbol: str, date: str, start: int = 0, count: int = 800) -> Optional[List[TickData]]:
        """获取历史逐笔成交

        Args:
            symbol: 股票代码
            date: 日期 YYYYMMDD
            start: 起始位置
            count: 数量 (max 800 per call)
        Returns:
            TickData list or None
        """
        if not self.is_available():
            return None
        try:
            market, code = self._normalize_symbol(symbol)
            df = self.client.transactions(symbol=code, start=start, count=count, date=date)

            if df is None or df.empty:
                return None

            price_div = 100.0
            results = []
            for _, row in df.iterrows():
                direction = ''
                buy_or_sell = row.get('buyorsell', 0)
                if buy_or_sell == 0:
                    direction = '买盘'
                elif buy_or_sell == 1:
                    direction = '卖盘'
                else:
                    direction = '中性'

                results.append(TickData(
                    time=str(row.get('time', '')),
                    price=float(row.get('price', 0)) / price_div,
                    volume=int(row.get('vol', 0)),
                    amount=float(row.get('price', 0)) / price_div * int(row.get('vol', 0)),
                    direction=direction,
                ))
            return results
        except Exception as e:
            log_error(f"TdxProvider.transaction_history error for {symbol}: {e}")
            return None

    # ========== 财务快照 ==========

    def finance(self, symbol: str) -> Optional[FinanceSnapshotData]:
        """获取财务快照 (mootdx client.finance)

        Returns: FinanceSnapshotData with 流通股本/总股本/总资产/净资产/EPS/每股净资产/股东人数/上市日期/行业
        """
        if not self.is_available():
            return None
        try:
            market, code = self._normalize_symbol(symbol)
            df = self.client.finance(symbol=code)

            if df is None or df.empty:
                return None

            row = df.iloc[0]
            std_symbol = f"SH{code}" if market == MARKET_SH else f"SZ{code}"

            def _safe_float(val, default=None):
                try:
                    v = row.get(val, default)
                    if v is None or (isinstance(v, float) and v != v):  # NaN check
                        return default
                    return float(v)
                except (ValueError, TypeError):
                    return default

            def _safe_int(val, default=None):
                try:
                    v = row.get(val, default)
                    if v is None or (isinstance(v, float) and v != v):
                        return default
                    return int(v)
                except (ValueError, TypeError):
                    return default

            return FinanceSnapshotData(
                symbol=std_symbol,
                circulating_share=_safe_float('liutongguben'),
                total_share=_safe_float('zongguben'),
                total_assets=_safe_float('zongzichan'),
                net_assets=_safe_float('jingzichan'),
                main_revenue=_safe_float('zhuyingshouru'),
                net_profit=_safe_float('jinglirun'),
                eps=_safe_float('meigushouyi'),
                bvps=_safe_float('meigujingzichan'),
                shareholder_count=_safe_int('gudongrenshu'),
                list_date=str(row.get('ipo_date', '')) if row.get('ipo_date') else None,
                industry=str(row.get('industry', '')) if row.get('industry') else None,
                source=self.name,
            )
        except Exception as e:
            log_error(f"TdxProvider.finance error for {symbol}: {e}")
            return None

    # ========== F10 数据 ==========

    def f10_categories(self, symbol: str) -> Optional[List[Dict]]:
        """获取F10分类列表 (mootdx client.F10C)

        Returns: [{'name': '公司概况', ...}, ...]
        """
        if not self.is_available():
            return None
        try:
            market, code = self._normalize_symbol(symbol)
            result = self.client.F10C(symbol=code)

            if result is None or (hasattr(result, 'empty') and result.empty):
                return None

            categories = []
            if isinstance(result, list):
                for item in result:
                    if isinstance(item, dict):
                        categories.append({
                            'name': item.get('name', ''),
                            'filename': item.get('filename', ''),
                        })
                    else:
                        categories.append({'name': str(item)})
            elif hasattr(result, 'iterrows'):
                for _, row in result.iterrows():
                    categories.append({
                        'name': row.get('name', ''),
                        'filename': row.get('filename', ''),
                    })
            return categories if categories else None
        except Exception as e:
            log_error(f"TdxProvider.f10_categories error for {symbol}: {e}")
            return None

    def f10_detail(self, symbol: str, name: str) -> Optional[List[Dict]]:
        """获取F10分类详情 (mootdx client.F10)

        Args:
            symbol: 股票代码
            name: 分类名称 (from f10_categories)
        Returns: list of key-value dicts
        """
        if not self.is_available():
            return None
        try:
            market, code = self._normalize_symbol(symbol)
            result = self.client.F10(symbol=code, name=name)

            if result is None:
                return None

            # F10 返回文本字符串, 按行解析
            if isinstance(result, str):
                lines = [l.strip() for l in result.split('\n') if l.strip()]
                return [{'content': line} for line in lines]

            # 如果返回的是 dict (name->content)
            if isinstance(result, dict):
                items = []
                for k, v in result.items():
                    items.append({'category': k, 'content': str(v)})
                return items

            # DataFrame
            if hasattr(result, 'iterrows'):
                items = []
                for _, row in result.iterrows():
                    items.append(dict(row))
                return items

            return None
        except Exception as e:
            log_error(f"TdxProvider.f10_detail error for {symbol}: {e}")
            return None

    # ========== 除权除息 ==========

    def xdxr(self, symbol: str) -> Optional[List[XdxrData]]:
        """获取除权除息数据 (mootdx client.xdxr)

        Returns: List of XdxrData
        """
        if not self.is_available():
            return None
        try:
            market, code = self._normalize_symbol(symbol)
            df = self.client.xdxr(symbol=code)

            if df is None or df.empty:
                return None

            std_symbol = f"SH{code}" if market == MARKET_SH else f"SZ{code}"
            price_div = 100.0
            results = []

            for _, row in df.iterrows():
                # mootdx xdxr 字段: category/bonus_share/conver_share/cash_div/allot_share/allot_price/date/code
                # category: 1=除权, 2=除息, 3=除权除息
                cat = int(row.get('category', 0))
                cat_name = {1: '除权', 2: '除息', 3: '除权除息'}.get(cat, '其他')

                results.append(XdxrData(
                    symbol=std_symbol,
                    date=str(row.get('date', '')),
                    category=cat_name,
                    bonus_share=float(row.get('bonus_share', 0)) / price_div if row.get('bonus_share') else 0,
                    conver_share=float(row.get('conver_share', 0)) / price_div if row.get('conver_share') else 0,
                    cash_div=float(row.get('cash_div', 0)) / price_div if row.get('cash_div') else 0,
                    allot_share=float(row.get('allot_share', 0)) / price_div if row.get('allot_share') else 0,
                    allot_price=float(row.get('allot_price', 0)) / price_div if row.get('allot_price') else 0,
                    source=self.name,
                ))
            return results
        except Exception as e:
            log_error(f"TdxProvider.xdxr error for {symbol}: {e}")
            return None


# 全局实例
tdx_provider: Optional[TdxProvider] = None


def get_tdx_provider() -> TdxProvider:
    """获取全局TdxProvider"""
    global tdx_provider
    if tdx_provider is None:
        tdx_provider = TdxProvider()
    return tdx_provider


if __name__ == '__main__':
    # 测试
    print("Testing TdxProvider...")
    
    provider = TdxProvider()
    
    if provider.is_available():
        # 测试实时行情
        print("\n✓ Testing quote:")
        quote = provider.quote('600519')  # 茅台
        if quote:
            print(f"  {quote.symbol}: {quote.name} @ {quote.current:.2f} ({quote.percent:+.2f}%)")
        
        # 测试批量行情
        print("\n✓ Testing batch quote:")
        quotes = provider.batch_quote(['600519', '000001'])
        for q in quotes:
            print(f"  {q.symbol}: {q.name} @ {q.current:.2f}")
        
        # 测试K线
        print("\n✓ Testing kline:")
        klines = provider.kline('600519', period='day', count=5)
        if klines:
            for k in klines[:3]:
                print(f"  {k.date}: {k.open:.2f} - {k.high:.2f} - {k.low:.2f} - {k.close:.2f}")
    else:
        print("✗ TdxProvider not available")
    
    provider.close()
    print("\n✓ TdxProvider test done!")
