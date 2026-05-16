#!/usr/bin/env python3
"""
BaseProvider - Provider基类
所有数据源Provider必须继承此类
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
import time

from teakfds.models import (
    QuoteData, DepthData, KlineData, IntradayData,
    IncomeData, BalanceData, CashFlowData, FinancialIndicator,
    ValuationData, ProviderStatus
)


@dataclass
class ProviderCapabilities:
    """Provider能力声明"""
    supports_quote: bool = False
    supports_depth: bool = False
    supports_intraday: bool = False
    supports_kline: bool = False
    supports_financial: bool = False
    supports_valuation: bool = False
    supports_news: bool = False
    supports_tick: bool = False              # 逐笔成交
    supports_finance_snapshot: bool = False  # 财务快照 (mootdx finance)
    supports_f10: bool = False               # F10公司资料
    supports_xdxr: bool = False             # 除权除息
    supports_report: bool = False           # 研报
    supports_announcement: bool = False      # 公告
    supports_money_flow: bool = False        # 资金流向
    supports_iwencai: bool = False          # 问财NL查询

    # 支持的市场
    markets: List[str] = None  # ['a_share', 'hk', 'us']

    # 支持的K线周期
    kline_periods: List[str] = None  # ['1min', '5min', 'day', 'week', 'month']
    
    def __post_init__(self):
        if self.markets is None:
            self.markets = []
        if self.kline_periods is None:
            self.kline_periods = []


class BaseProvider(ABC):
    """
    Provider基类
    
    所有数据源Provider必须继承此类并实现相应接口。
    每个Provider负责封装一个具体的数据源。
    """
    
    # Provider基本信息 (子类必须覆盖)
    name: str = "base"
    display_name: str = "Base Provider"
    
    # 优先级 (越大越优先)
    priority: int = 0
    
    # 能力声明 (子类应覆盖)
    capabilities: ProviderCapabilities = ProviderCapabilities()
    
    def __init__(self):
        self._available: Optional[bool] = None
        self._last_check_time: float = 0
        self._check_interval: int = 300  # 可用性检查间隔 (秒)
    
    # ========== 核心接口 ==========
    
    @abstractmethod
    def is_available(self) -> bool:
        """
        检查Provider是否可用
        
        Returns:
            True 如果数据源可用
        """
        pass
    
    @abstractmethod
    def get_status(self) -> ProviderStatus:
        """
        获取Provider健康状态
        
        Returns:
            ProviderStatus 对象
        """
        pass
    
    # ========== 实时行情接口 ==========
    
    def quote(self, symbol: str) -> Optional[QuoteData]:
        """
        获取实时行情
        
        Args:
            symbol: 股票代码
        
        Returns:
            QuoteData 或 None
        """
        raise NotImplementedError(f"{self.name} does not support quote()")
    
    def batch_quote(self, symbols: List[str]) -> List[QuoteData]:
        """
        批量获取实时行情
        
        Args:
            symbols: 股票代码列表
        
        Returns:
            QuoteData 列表
        """
        # 默认实现：逐个获取
        results = []
        for symbol in symbols:
            quote = self.quote(symbol)
            if quote:
                results.append(quote)
        return results
    
    def depth(self, symbol: str) -> Optional[DepthData]:
        """
        获取盘口数据
        
        Args:
            symbol: 股票代码
        
        Returns:
            DepthData 或 None
        """
        raise NotImplementedError(f"{self.name} does not support depth()")
    
    def intraday(self, symbol: str) -> Optional[List[IntradayData]]:
        """
        获取分时数据
        
        Args:
            symbol: 股票代码
        
        Returns:
            IntradayData 列表或None
        """
        raise NotImplementedError(f"{self.name} does not support intraday()")
    
    # ========== K线接口 ==========
    
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
            KlineData 列表或None
        """
        raise NotImplementedError(f"{self.name} does not support kline()")
    
    def kline_adjusted(self,
                       symbol: str,
                       period: str = 'day',
                       adjust: str = 'qfq') -> Optional[List[KlineData]]:
        """
        获取复权K线
        
        Args:
            symbol: 股票代码
            period: 周期
            adjust: 复权类型 ('qfq'=前复权, 'hfq'=后复权, 'none'=不复权)
        
        Returns:
            KlineData 列表或None
        """
        raise NotImplementedError(f"{self.name} does not support kline_adjusted()")
    
    # ========== 财务数据接口 ==========
    
    def income(self, symbol: str, period: str = None) -> Optional[IncomeData]:
        """
        获取利润表
        
        Args:
            symbol: 股票代码
            period: 报告期 (YYYYMMDD)，None为最新
        
        Returns:
            IncomeData 或None
        """
        raise NotImplementedError(f"{self.name} does not support income()")
    
    def balance_sheet(self, symbol: str, period: str = None) -> Optional[BalanceData]:
        """获取资产负债表"""
        raise NotImplementedError(f"{self.name} does not support balance_sheet()")
    
    def cash_flow(self, symbol: str, period: str = None) -> Optional[CashFlowData]:
        """获取现金流量表"""
        raise NotImplementedError(f"{self.name} does not support cash_flow()")
    
    def financial_indicator(self, symbol: str, period: str = None) -> Optional[FinancialIndicator]:
        """获取财务指标"""
        raise NotImplementedError(f"{self.name} does not support financial_indicator()")
    
    def dividend(self, symbol: str) -> Optional[List[Dict]]:
        """获取分红数据"""
        raise NotImplementedError(f"{self.name} does not support dividend()")
    
    # ========== 估值数据接口 ==========
    
    def valuation(self, symbol: str) -> Optional[ValuationData]:
        """
        获取估值数据
        
        Args:
            symbol: 股票代码
        
        Returns:
            ValuationData 或None
        """
        raise NotImplementedError(f"{self.name} does not support valuation()")
    
    def valuation_history(self, symbol: str, years: int = 10) -> Optional[List[Dict]]:
        """获取历史估值数据"""
        raise NotImplementedError(f"{self.name} does not support valuation_history()")
    
    # ========== 市场数据接口 ==========
    
    def index_components(self, index_code: str) -> Optional[List[str]]:
        """获取指数成分股"""
        raise NotImplementedError(f"{self.name} does not support index_components()")
    
    def money_flow(self, symbol: str, days: int = 30) -> Optional[List[Dict]]:
        """获取资金流向"""
        raise NotImplementedError(f"{self.name} does not support money_flow()")
    
    # ========== 资讯数据接口 ==========
    
    def news(self, symbol: str = None, days: int = 7) -> Optional[List[Dict]]:
        """获取新闻"""
        raise NotImplementedError(f"{self.name} does not support news()")
    
    # ========== 辅助方法 ==========
    
    def _check_available(self) -> bool:
        """
        内部可用性检查 (带缓存)
        """
        now = time.time()
        
        # 如果检查间隔内，返回缓存结果
        if self._available is not None and (now - self._last_check_time) < self._check_interval:
            return self._available
        
        # 执行实际检查
        try:
            self._available = self._do_check_available()
            self._last_check_time = now
        except Exception as e:
            print(f"{self.name} availability check failed: {e}")
            self._available = False
        
        return self._available
    
    def _do_check_available(self) -> bool:
        """
        实际的可用性检查 (子类可覆盖)
        """
        return True
    
    def supports_market(self, market: str) -> bool:
        """检查是否支持指定市场"""
        return market in (self.capabilities.markets or [])
    
    def supports_kline_period(self, period: str) -> bool:
        """检查是否支持指定K线周期"""
        return period in (self.capabilities.kline_periods or [])
    
    def get_info(self) -> Dict[str, Any]:
        """获取Provider信息"""
        return {
            'name': self.name,
            'display_name': self.display_name,
            'priority': self.priority,
            'available': self.is_available(),
            'capabilities': {
                'quote': self.capabilities.supports_quote,
                'depth': self.capabilities.supports_depth,
                'intraday': self.capabilities.supports_intraday,
                'kline': self.capabilities.supports_kline,
                'financial': self.capabilities.supports_financial,
                'valuation': self.capabilities.supports_valuation,
                'markets': self.capabilities.markets,
                'kline_periods': self.capabilities.kline_periods,
            }
        }


class RealtimeProvider(BaseProvider):
    """
    实时数据Provider基类
    专注于实时行情、盘口、分时等数据
    """
    
    capabilities = ProviderCapabilities(
        supports_quote=True,
        supports_depth=True,
        supports_intraday=True,
        supports_kline=True,
        markets=['a_share'],
        kline_periods=['1min', '5min', '15min', '30min', '60min']
    )


class HistoricalProvider(BaseProvider):
    """
    历史数据Provider基类
    专注于日线、周线、月线等历史数据
    """
    
    capabilities = ProviderCapabilities(
        supports_kline=True,
        supports_financial=True,
        markets=['a_share'],
        kline_periods=['day', 'week', 'month']
    )


class FinancialProvider(BaseProvider):
    """
    财务数据Provider基类
    专注于财务报表、估值等数据
    """
    
    capabilities = ProviderCapabilities(
        supports_financial=True,
        supports_valuation=True,
        markets=['a_share']
    )


class CompositeProvider(BaseProvider):
    """
    复合Provider
    可以组合多个Provider的能力
    """
    
    def __init__(self, providers: List[BaseProvider] = None):
        super().__init__()
        self.providers = providers or []
    
    def add_provider(self, provider: BaseProvider):
        """添加Provider"""
        self.providers.append(provider)
    
    def is_available(self) -> bool:
        """任意一个Provider可用即可"""
        return any(p.is_available() for p in self.providers)
    
    def get_status(self) -> ProviderStatus:
        """返回最健康Provider的状态"""
        for provider in self.providers:
            if provider.is_available():
                return provider.get_status()
        
        return ProviderStatus(
            name=self.name,
            available=False
        )
    
    def quote(self, symbol: str) -> Optional[QuoteData]:
        """尝试所有Provider"""
        for provider in self.providers:
            if provider.is_available() and provider.capabilities.supports_quote:
                try:
                    result = provider.quote(symbol)
                    if result:
                        return result
                except Exception as e:
                    print(f"{provider.name} quote error: {e}")
        return None


if __name__ == '__main__':
    # 测试
    print("Testing BaseProvider...")
    
    # 创建一个测试Provider
    class TestProvider(RealtimeProvider):
        name = "test"
        display_name = "Test Provider"
        priority = 10
        
        def is_available(self) -> bool:
            return True
        
        def get_status(self) -> ProviderStatus:
            return ProviderStatus(
                name=self.name,
                available=True,
                last_success=datetime.now().isoformat()
            )
        
        def quote(self, symbol: str) -> Optional[QuoteData]:
            return QuoteData(
                symbol=symbol,
                name='测试股票',
                current=100.0,
                open=99.0,
                high=101.0,
                low=98.0,
                close=99.0,
                volume=1000000,
                amount=100000000,
                percent=1.01,
                timestamp=datetime.now().isoformat(),
                source=self.name
            )
    
    provider = TestProvider()
    
    print(f"\n✓ Provider info:")
    print(f"  Name: {provider.name}")
    print(f"  Available: {provider.is_available()}")
    print(f"  Capabilities: {provider.capabilities}")
    
    print(f"\n✓ Testing quote:")
    quote = provider.quote('SH600519')
    if quote:
        print(f"  {quote.symbol}: {quote.name} @ {quote.current}")
    
    print(f"\n✓ Provider info dict:")
    info = provider.get_info()
    for k, v in info.items():
        print(f"  {k}: {v}")
    
    print("\n✓ BaseProvider test passed!")
