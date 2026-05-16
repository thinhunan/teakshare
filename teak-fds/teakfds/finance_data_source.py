#!/usr/bin/env python3
"""
FinanceDataSource / TeakFDS — 统一金融数据源（teak-fds skill 核心）。

包路径：`teakfds.finance_data_source`。Agent 请使用 `from teakfds import TeakFDS`。

使用方式:
    from teakfds import TeakFDS

    source = TeakFDS()
    quote = source.quote('SH600519')
    kline = source.kline('SH600519', period='day', count=30)
"""

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List, Dict, Union, Any
from dataclasses import dataclass

from teakfds.datasource_log import log_info, log_warn, log_error

from teakfds.tushare_table import is_null, records_empty, coerce_tushare_table

from teakfds.models import (
    QuoteData, DepthData, KlineData, IntradayData,
    IncomeData, BalanceData, CashFlowData, FinancialIndicator,
    ValuationData, NewsData, ProviderStatus,
    TickData, FinanceSnapshotData, XdxrData,
    detect_market, normalize_symbol, parse_symbol_input,
)
from teakfds.cache_manager import CacheManager, get_cache_manager
from teakfds.rate_limiter import RateLimiter, get_rate_limiter
from teakfds.router import Router, SmartRouter, get_router, DataType

from teakfds.providers import (
    BaseProvider,
    get_all_providers,
    get_provider_by_name,
)


class FinanceDataSource:
    """统一金融数据源

    功能:
    - 统一API接口
    - 智能路由选择数据源
    - 自动降级
    - 限流保护
    - 缓存管理

    更新: 2026-04-15
    - DataProxy重命名为FinanceDataSource
    - 新增腾讯财经P0主源
    - 新增新浪财经P2备份
    - 整合mx-data为P3备份
    - 整合mx-search为P0搜索
    """

    CACHE_TTL = {
        'quote': 60,
        'depth': 30,
        'intraday': 60,
        'kline': 86400,
        'financial': 604800,
        'valuation': 86400,
        'news': 3600,
        'search': 1800,
        'tick': 30,
        'finance_snapshot': 86400,
        'f10': 86400,
        'xdxr': 86400,
        'report': 3600,
        'announcement': 1800,
    }

    def __init__(self, use_cache=True, use_smart_router=True):
        """
        Args:
            use_cache: 是否启用缓存
            use_smart_router: 是否使用智能路由
        """
        self.router = SmartRouter() if use_smart_router else Router()
        self.cache = get_cache_manager() if use_cache else CacheManager(max_size=0)
        self.rate_limiter = get_rate_limiter()
        
        self._providers = {}
        self._init_providers()

    @staticmethod
    def _resolve_symbol(symbol: str) -> str:
        """解析「名称（代码）」等自然语言输入为可路由代码（如 腾讯控股（00700）→ 00700）。"""
        if symbol is None:
            return symbol
        return parse_symbol_input(symbol)
    
    def _init_providers(self):
        """注册所有Provider工厂（延迟实例化）"""
        self._provider_factories = {
            # P0 - 高优先级
            'tencent': lambda: get_provider_by_name('tencent'),
            'tdx': lambda: get_provider_by_name('tdx'),
            'mx_search': lambda: get_provider_by_name('mx_search'),
            # P-1 - Qlib量化数据（最高优先级A股日线）
            'qlib': lambda: get_provider_by_name('qlib'),
            # P1 - 历史数据主源
            'tushare': lambda: get_provider_by_name('tushare'),
            # P0 - 估值
            'lixinger': lambda: get_provider_by_name('lixinger'),
            # P2 - 备份
            'sina': lambda: get_provider_by_name('sina'),
            # P3 - 低优先级备份
            'mx_data': lambda: get_provider_by_name('mx_data'),
            # P4 - 雪球备份
            'xueqiu': lambda: get_provider_by_name('xueqiu'),
            # P5 - 搜索兜底
            'search_fallback': lambda: get_provider_by_name('search_fallback'),
            # P6 - 研报+公告
            'aggregate': lambda: get_provider_by_name('aggregate'),
            'iwencai': lambda: get_provider_by_name('iwencai'),
            'cninfo': lambda: get_provider_by_name('cninfo'),
            # P7 - 补充数据源 (百度/同花顺/东财直调)
            'baidu': lambda: get_provider_by_name('baidu'),
            'ths': lambda: get_provider_by_name('ths'),
            'eastmoney': lambda: get_provider_by_name('eastmoney'),
        }
    
    def _register_provider(self, name, factory):
        """注册Provider（已弃用，保留兼容）"""
        try:
            provider = factory()
            if provider and provider.is_available():
                self._providers[name] = provider
                log_info(f"✓ Provider registered: {name} (priority={provider.priority})")
        except Exception as e:
            log_error(f"✗ Failed to register {name}: {e}")
    
    def get_provider(self, name: str) -> Optional[BaseProvider]:
        """获取Provider（延迟加载）"""
        # 1. 检查已实例化的缓存
        if name in self._providers:
            return self._providers[name]
        
        # 2. 从工厂创建（延迟加载）
        factory = self._provider_factories.get(name) if hasattr(self, '_provider_factories') else None
        if factory:
            try:
                provider = factory()
                if provider and provider.is_available():
                    self._providers[name] = provider
                    log_info(f"✓ Provider loaded: {name} (priority={provider.priority})")
                    return provider
            except Exception as e:
                log_error(f"✗ Failed to load {name}: {e}")
        
        # 3. 回退：直接调用 get_provider_by_name
        provider = get_provider_by_name(name)
        if provider and provider.is_available():
            self._providers[name] = provider
            return provider
        
        return None
    
    # ========== 实时行情 API ==========
    
    def quote(self, symbol: str, use_cache: bool = True) -> Optional[QuoteData]:
        """获取实时行情"""
        symbol = self._resolve_symbol(symbol)
        cache_key = f"quote:{symbol}"
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached:
                return QuoteData(**cached)
        
        route = self.router.route_quote(symbol)
        
        last_error = None
        for provider_name in route.providers:
            provider = self.get_provider(provider_name)
            if not provider:
                continue
            
            if not self.rate_limiter.check(provider_name):
                continue
            
            try:
                start_time = time.time()
                result = provider.quote(symbol)
                latency = (time.time() - start_time) * 1000
                
                if result:
                    self.rate_limiter.record_request(provider_name)
                    if isinstance(self.router, SmartRouter):
                        self.router.record_result(provider_name, True, latency)
                    
                    if use_cache:
                        self.cache.set(cache_key, result.to_dict(), 
                                      data_type='quote', ttl=self.CACHE_TTL['quote'])
                    
                    return result
                    
            except Exception as e:
                last_error = e
                self.rate_limiter.record_failure(provider_name)
                if isinstance(self.router, SmartRouter):
                    self.router.record_result(provider_name, False, 0)
                continue
        
        if last_error:
            log_error(f"FinanceDataSource.quote failed for {symbol}: {last_error}")
        
        return None
    
    def batch_quote(self, symbols: List[str], use_cache: bool = True) -> List[QuoteData]:
        """批量获取行情（优化：优先使用 Tencent 批量接口，一次请求多只股票）

        Args:
            symbols: 股票代码列表
            use_cache: 是否使用缓存
        """
        if not symbols:
            return []

        symbols = [self._resolve_symbol(s) for s in symbols]

        cached_results: Dict[str, QuoteData] = {}
        missing: List[str] = []

        if use_cache:
            for sym in symbols:
                c = self.cache.get(f"quote:{sym}")
                if c:
                    try:
                        cached_results[sym] = QuoteData(**c)
                        continue
                    except Exception:
                        pass
                missing.append(sym)
        else:
            missing = list(symbols)

        # 尝试使用 tencent 的批量接口（单次 HTTP 请求）
        if missing:
            tencent = self.get_provider('tencent')
            if tencent and hasattr(tencent, 'batch_quote') and self.rate_limiter.check('tencent'):
                try:
                    start_time = time.time()
                    batch_res = tencent.batch_quote(missing) or []
                    latency = (time.time() - start_time) * 1000
                    self.rate_limiter.record_request('tencent')
                    if isinstance(self.router, SmartRouter):
                        self.router.record_result('tencent', True, latency)
                    got_keys = set()
                    for q in batch_res:
                        key = q.symbol if hasattr(q, 'symbol') else None
                        if key:
                            cached_results[key] = q
                            got_keys.add(key)
                            if use_cache:
                                self.cache.set(f"quote:{key}", q.to_dict(),
                                               data_type='quote',
                                               ttl=self.CACHE_TTL['quote'])
                    # 未能匹配的 symbol 继续走单次 fallback
                    missing = [s for s in missing
                               if s not in got_keys and s not in cached_results]
                except Exception as e:
                    self.rate_limiter.record_failure('tencent')
                    if isinstance(self.router, SmartRouter):
                        self.router.record_result('tencent', False, 0)
                    log_error(f"FinanceDataSource.batch_quote tencent error: {e}")

        # 剩余的逐个走标准 quote() 流程（自动路由）
        for sym in missing:
            q = self.quote(sym, use_cache=use_cache)
            if q:
                cached_results[sym] = q

        # 按原顺序返回
        return [cached_results[s] for s in symbols if s in cached_results]

    # ========== 盘口数据 API ==========
    
    def depth(self, symbol: str) -> Optional[DepthData]:
        """获取盘口数据"""
        symbol = self._resolve_symbol(symbol)
        cache_key = f"depth:{symbol}"
        cached = self.cache.get(cache_key)
        if cached:
            return DepthData(**cached)
        
        route = self.router.route(DataType.DEPTH, symbol)
        
        for provider_name in route.providers:
            provider = self.get_provider(provider_name)
            if not provider or not provider.capabilities.supports_depth:
                continue
            
            try:
                result = provider.depth(symbol)
                if result:
                    self.cache.set(cache_key, result.to_dict(), 
                                  data_type='depth', ttl=self.CACHE_TTL['depth'])
                    return result
            except Exception as e:
                log_error(f"FinanceDataSource.depth error from {provider_name}: {e}")
                continue
        
        return None
    
    # ========== 分时/盘口 API ==========

    def intraday(self, symbol: str, use_cache: bool = True) -> Optional[List[IntradayData]]:
        """获取当日分时数据（按 INTRADAY 路由）

        Args:
            symbol: 股票代码
            use_cache: 是否使用缓存
        """
        symbol = self._resolve_symbol(symbol)
        cache_key = f"intraday:{symbol}"
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached:
                return [IntradayData(**d) for d in cached]

        route = self.router.route(DataType.INTRADAY, symbol)
        for provider_name in route.providers:
            provider = self.get_provider(provider_name)
            if not provider:
                continue
            if not self.rate_limiter.check(provider_name):
                continue
            if not getattr(provider.capabilities, 'supports_intraday', False):
                continue
            try:
                start_time = time.time()
                result = provider.intraday(symbol)
                latency = (time.time() - start_time) * 1000
                if result:
                    self.rate_limiter.record_request(provider_name)
                    if isinstance(self.router, SmartRouter):
                        self.router.record_result(provider_name, True, latency)
                    if use_cache:
                        self.cache.set(
                            cache_key,
                            [d.to_dict() for d in result],
                            data_type='intraday',
                            ttl=self.CACHE_TTL['intraday']
                        )
                    return result
            except Exception as e:
                self.rate_limiter.record_failure(provider_name)
                if isinstance(self.router, SmartRouter):
                    self.router.record_result(provider_name, False, 0)
                log_error(f"FinanceDataSource.intraday error from {provider_name}: {e}")
                continue
        return None

    def minute_kline(self, symbol: str, period: str = '1d') -> Optional[Dict]:
        """获取分时图数据（雪球原始返回）

        Args:
            symbol: 股票代码
            period: '1d'（当日）或 '5d'（5日）
        """
        symbol = self._resolve_symbol(symbol)
        provider = self.get_provider('xueqiu')
        if provider and hasattr(provider, 'minute'):
            try:
                return provider.minute(symbol, period=period)
            except Exception as e:
                log_error(f"FinanceDataSource.minute_kline error: {e}")
        return None

    def pankou(self, symbol: str) -> Optional[Dict]:
        """获取雪球原始盘口数据（bp1~bp10/sp1~sp10/wei_bi 等字段）

        Args:
            symbol: 股票代码
        """
        symbol = self._resolve_symbol(symbol)
        provider = self.get_provider('xueqiu')
        if provider and hasattr(provider, 'pankou'):
            try:
                return provider.pankou(symbol)
            except Exception as e:
                log_error(f"FinanceDataSource.pankou error: {e}")
        return None

    # ========== K线数据 API ==========

    def kline(
        self,
        symbol: str,
        period: str = 'day',
        count: int = 30,
        start_date: str = None,
        end_date: str = None,
        use_cache: bool = True,
        adj: Optional[str] = None,
    ) -> Optional[List[KlineData]]:
        """获取历史 K 线。

        Args:
            adj: 仅对 **A 股 / 港股日线** 生效。``None`` 时走原有智能路由；显式传入
                ``'none'`` / ``'qfq'`` / ``'hfq'`` 时：**优先 Tushare**（未复权日线或
                ``pro_bar`` 复权），失败则走路由器（腾讯 / 雪球 / 妙想等）。无本地 SQLite 依赖。
        """
        symbol = self._resolve_symbol(symbol)
        cache_key = f"kline:{symbol}:{period}:{start_date}:{end_date}:{count}:adj={adj}"
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached:
                return [KlineData(**k) for k in cached]

        market = detect_market(symbol)
        if period == 'day' and adj is not None and market in ('a_share', 'hk'):
            got = self._kline_daily_adj_composite(
                symbol, count, start_date, end_date, use_cache, adj, cache_key, market
            )
            if got:
                return got

        return self._kline_via_router(
            symbol, period, count, start_date, end_date, use_cache, cache_key
        )

    def _kline_via_router(
        self,
        symbol: str,
        period: str,
        count: int,
        start_date: str,
        end_date: str,
        use_cache: bool,
        cache_key: str,
    ) -> Optional[List[KlineData]]:
        route = self.router.route_kline(
            symbol,
            period=period,
            estimated_rows=max(int(count or 0), 0),
            large_batch=(int(count or 0) > 500),
        )
        for provider_name in route.providers:
            provider = self.get_provider(provider_name)
            if not provider:
                continue
            if not self.rate_limiter.check(provider_name):
                continue
            try:
                start_time = time.time()
                result = provider.kline(symbol, period, count, start_date, end_date)
                latency = (time.time() - start_time) * 1000
                if result:
                    self.rate_limiter.record_request(provider_name)
                    if isinstance(self.router, SmartRouter):
                        self.router.record_result(provider_name, True, latency)
                    if use_cache:
                        self.cache.set(
                            cache_key,
                            [k.to_dict() for k in result],
                            data_type='kline',
                            ttl=self.CACHE_TTL['kline'],
                        )
                    return result
            except Exception:
                self.rate_limiter.record_failure(provider_name)
                if isinstance(self.router, SmartRouter):
                    self.router.record_result(provider_name, False, 0)
                continue
        return None

    def _kline_daily_adj_composite(
        self,
        symbol: str,
        count: int,
        start_date: str,
        end_date: str,
        use_cache: bool,
        adj: str,
        cache_key: str,
        market: str,
    ) -> Optional[List[KlineData]]:
        """显式 adj 时的日线：优先 Tushare，失败走路由器（无本地库）。"""
        adj_norm = adj.strip().lower()
        if adj_norm not in ('none', 'qfq', 'hfq'):
            adj_norm = 'none'

        if market == 'hk' and adj_norm in ('qfq', 'hfq'):
            return self._kline_via_router(
                symbol, 'day', count, start_date, end_date, use_cache, cache_key
            )

        if market == 'hk' and adj_norm == 'none':
            return self._kline_via_router(
                symbol, 'day', count, start_date, end_date, use_cache, cache_key
            )

        tu = self.get_provider('tushare')

        if market == 'a_share' and adj_norm in ('qfq', 'hfq'):
            pb = self._kline_from_tushare_pro_bar(
                symbol, count, start_date, end_date, adj_norm
            )
            if pb:
                if use_cache:
                    self.cache.set(
                        cache_key,
                        [k.to_dict() for k in pb],
                        data_type='kline',
                        ttl=self.CACHE_TTL['kline'],
                    )
                return pb

            return self._kline_via_router(
                symbol, 'day', count, start_date, end_date, use_cache, cache_key
            )

        if market == 'a_share' and adj_norm == 'none':
            raw = None
            if tu and tu.is_available() and self.rate_limiter.check('tushare'):
                try:
                    st0 = time.time()
                    raw = tu.kline(symbol, 'day', count, start_date, end_date)
                    lat = (time.time() - st0) * 1000
                    if raw:
                        self.rate_limiter.record_request('tushare')
                        if isinstance(self.router, SmartRouter):
                            self.router.record_result('tushare', True, lat)
                    else:
                        if isinstance(self.router, SmartRouter):
                            self.router.record_result('tushare', False, 0)
                except Exception:
                    self.rate_limiter.record_failure('tushare')
                    if isinstance(self.router, SmartRouter):
                        self.router.record_result('tushare', False, 0)
                    raw = None

            if raw:
                if use_cache:
                    self.cache.set(
                        cache_key,
                        [k.to_dict() for k in raw],
                        data_type='kline',
                        ttl=self.CACHE_TTL['kline'],
                    )
                return raw

            return self._kline_via_router(
                symbol, 'day', count, start_date, end_date, use_cache, cache_key
            )

        return self._kline_via_router(
            symbol, 'day', count, start_date, end_date, use_cache, cache_key
        )

    def _kline_from_tushare_pro_bar(
        self,
        symbol: str,
        count: int,
        start_date: str,
        end_date: str,
        adj: str,
    ) -> Optional[List[KlineData]]:
        from datetime import datetime, timedelta

        tu = self.get_provider('tushare')
        if not tu or not tu.is_available():
            return None
        if not self.rate_limiter.check('tushare'):
            return None
        if not end_date:
            end_date = datetime.now().strftime('%Y%m%d')
        if not start_date:
            start_date = (datetime.now() - timedelta(days=max(400, count * 3))).strftime('%Y%m%d')
        ts_code = tu.normalize_code(symbol)
        try:
            st = time.time()
            rows = tu.get_pro_bar(ts_code, start_date=start_date, end_date=end_date, adj=adj, freq='D')
            if records_empty(rows):
                self.rate_limiter.record_failure('tushare')
                return None
            self.rate_limiter.record_request('tushare')
            if isinstance(self.router, SmartRouter):
                self.router.record_result('tushare', True, (time.time() - st) * 1000)
        except Exception:
            self.rate_limiter.record_failure('tushare')
            if isinstance(self.router, SmartRouter):
                self.router.record_result('tushare', False, 0)
            return None
        results = []
        for row in rows:
            if not isinstance(row, dict):
                row = dict(row)
            trade_date = str(row.get('trade_date', ''))
            if len(trade_date) == 8:
                date_str = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
            else:
                date_str = trade_date
            results.append(
                KlineData(
                    date=date_str,
                    open=float(row.get('open', 0)) if not is_null(row.get('open')) else 0,
                    high=float(row.get('high', 0)) if not is_null(row.get('high')) else 0,
                    low=float(row.get('low', 0)) if not is_null(row.get('low')) else 0,
                    close=float(row.get('close', 0)) if not is_null(row.get('close')) else 0,
                    volume=int(row.get('vol', 0)) if not is_null(row.get('vol')) else 0,
                    amount=float(row.get('amount', 0)) if not is_null(row.get('amount')) else 0,
                    pct_change=float(row.get('pct_chg', 0)) if not is_null(row.get('pct_chg')) else None,
                )
            )
        if count and len(results) > count:
            results = results[-count:]
        return results

    # ========== 财务数据 API ==========
    
    def income(self, symbol: str, period: str = None) -> Optional[IncomeData]:
        """获取利润表"""
        symbol = self._resolve_symbol(symbol)
        provider = self.get_provider('tushare')
        if provider and provider.capabilities.supports_financial:
            return provider.income(symbol, period)
        return None
    
    def balance_sheet(self, symbol: str, period: str = None) -> Optional[BalanceData]:
        """获取资产负债表"""
        symbol = self._resolve_symbol(symbol)
        provider = self.get_provider('tushare')
        if provider:
            return provider.balance_sheet(symbol, period)
        return None
    
    def cash_flow(self, symbol: str, period: str = None) -> Optional[CashFlowData]:
        """获取现金流量表"""
        symbol = self._resolve_symbol(symbol)
        provider = self.get_provider('tushare')
        if provider:
            return provider.cash_flow(symbol, period)
        return None
    
    def financial_indicator(self, symbol: str, period: str = None) -> Optional[FinancialIndicator]:
        """获取财务指标"""
        symbol = self._resolve_symbol(symbol)
        provider = self.get_provider('tushare')
        if provider:
            return provider.financial_indicator(symbol, period)
        return None

    def income_df(self, symbol: str, period: str = None):
        """获取利润表 (list[dict]，列名同 Tushare income 接口)"""
        symbol = self._resolve_symbol(symbol)
        provider = self.get_provider('tushare')
        if provider:
            try:
                ts_code = provider.normalize_code(symbol)
                return provider.get_income(ts_code, period)
            except Exception as e:
                log_error(f"FinanceDataSource.income_df error: {e}")
        return None

    def balance_sheet_df(self, symbol: str, period: str = None):
        """获取资产负债表 (list[dict])"""
        symbol = self._resolve_symbol(symbol)
        provider = self.get_provider('tushare')
        if provider:
            try:
                ts_code = provider.normalize_code(symbol)
                return provider.get_balancesheet(ts_code, period)
            except Exception as e:
                log_error(f"FinanceDataSource.balance_sheet_df error: {e}")
        return None

    def cash_flow_df(self, symbol: str, period: str = None):
        """获取现金流量表 (list[dict])"""
        symbol = self._resolve_symbol(symbol)
        provider = self.get_provider('tushare')
        if provider:
            try:
                ts_code = provider.normalize_code(symbol)
                return provider.get_cashflow(ts_code, period)
            except Exception as e:
                log_error(f"FinanceDataSource.cash_flow_df error: {e}")
        return None

    def pro_bar(self, symbol: str, start_date: str = None, end_date: str = None,
                adj: str = 'qfq', freq: str = 'D'):
        """获取复权行情 (list[dict]，列名同 Tushare 行情字段)

        Args:
            symbol: 股票代码
            start_date: 开始日期 YYYYMMDD
            end_date: 结束日期 YYYYMMDD
            adj: 复权类型 qfq(前复权)/hfq(后复权)/None(不复权)
            freq: 频率 D(日线)/W(周线)/M(月线)
        """
        symbol = self._resolve_symbol(symbol)
        provider = self.get_provider('tushare')
        if provider:
            try:
                ts_code = provider.normalize_code(symbol)
                return provider.get_pro_bar(ts_code, start_date, end_date, adj, freq)
            except Exception as e:
                log_error(f"FinanceDataSource.pro_bar error: {e}")
        return None

    # ========== 估值数据 API ==========
    
    def valuation(self, symbol: str, use_cache: bool = True) -> Optional[ValuationData]:
        """获取估值数据"""
        symbol = self._resolve_symbol(symbol)
        cache_key = f"valuation:{symbol}"
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached:
                return ValuationData(**cached)
        
        route = self.router.route_valuation(symbol)
        
        for provider_name in route.providers:
            provider = self.get_provider(provider_name)
            if not provider:
                continue
            
            try:
                result = provider.valuation(symbol)
                if result:
                    if use_cache:
                        self.cache.set(cache_key, result.to_dict(),
                                      data_type='valuation', ttl=self.CACHE_TTL['valuation'])
                    return result
            except Exception as e:
                log_error(f"FinanceDataSource.valuation error from {provider_name}: {e}")
                continue
        
        return None
    
    # ========== 搜索 API ==========

    def search(self, query: str, data_type: str = 'news') -> Optional[List[Dict]]:
        """执行金融搜索

        Args:
            query: 搜索关键词
            data_type: 搜索类型 ('news', 'report', 'announcement', 'all')
        """
        # 搜索是市场中性的，按默认 a_share 路由（mx_search/search_fallback 全市场一致）
        route = self.router.route(DataType.SEARCH, 'SH600000', query=query)

        for provider_name in route.providers:
            provider = self.get_provider(provider_name)
            if not provider:
                continue

            try:
                if provider_name == 'mx_search':
                    if data_type == 'news':
                        return provider.search_news(query)
                    elif data_type == 'report':
                        return provider.search_report(query)
                    elif data_type == 'announcement':
                        return provider.search_announcement(query)
                    else:
                        return provider.search(query)
                elif provider_name == 'search_fallback':
                    return provider.search(query)
            except Exception as e:
                log_error(f"FinanceDataSource.search error from {provider_name}: {e}")
                continue

        return None

    def search_news(self, query: str, days: int = 7) -> Optional[List[Dict]]:
        """搜索新闻

        Args:
            query: 搜索关键词
            days: 多少天内的新闻
        """
        provider = self.get_provider('mx_search')
        if provider:
            try:
                return provider.search_news(query, days=days)
            except Exception as e:
                log_error(f"FinanceDataSource.search_news error: {e}")
        return None

    def search_report(self, query: str) -> Optional[List[Dict]]:
        """搜索研报

        Args:
            query: 搜索关键词
        """
        provider = self.get_provider('mx_search')
        if provider:
            try:
                return provider.search_report(query)
            except Exception as e:
                log_error(f"FinanceDataSource.search_report error: {e}")
        return None

    def search_announcement(self, query: str, days: int = 30) -> Optional[List[Dict]]:
        """搜索公告

        Args:
            query: 搜索关键词
            days: 多少天内的公告
        """
        provider = self.get_provider('mx_search')
        if provider:
            try:
                return provider.search_announcement(query, days=days)
            except Exception as e:
                log_error(f"FinanceDataSource.search_announcement error: {e}")
        return None

    # ========== 扩展行情 API ==========

    def quote_ext(self, symbol: str, use_cache: bool = True) -> Optional[QuoteData]:
        """获取扩展行情 (含 PE/PB/换手率/市值)

        优先走腾讯(返回PE/PB/换手率/市值字段)，若腾讯不可用则走其他行情源+tdx财务快照补充。

        Args:
            symbol: 股票代码
            use_cache: 是否使用缓存

        Returns:
            QuoteData (含 pe_ttm/pb/turnover_rate/total_market_cap/circulating_market_cap/volume_ratio)
        """
        symbol = self._resolve_symbol(symbol)
        cache_key = f"quote_ext:{symbol}"
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached:
                return QuoteData(**cached)

        # 尝试腾讯 (已解析扩展字段)
        tencent = self.get_provider('tencent')
        if tencent and self.rate_limiter.check('tencent'):
            try:
                result = tencent.quote(symbol)
                if result and result.pe_ttm is not None:
                    self.rate_limiter.record_request('tencent')
                    if use_cache:
                        self.cache.set(cache_key, result.to_dict(),
                                      data_type='quote', ttl=self.CACHE_TTL['quote'])
                    return result
            except Exception as e:
                log_error(f"FinanceDataSource.quote_ext tencent error: {e}")

        # 回退: 标准行情 + tdx finance 补充
        q = self.quote(symbol, use_cache=use_cache)
        if q is None:
            return None

        # 尝试从 tdx finance 补充
        if q.pe_ttm is None:
            tdx = self.get_provider('tdx')
            if tdx and hasattr(tdx, 'finance'):
                try:
                    snap = tdx.finance(symbol)
                    if snap:
                        # 从财务快照计算 PE/PB
                        if snap.eps and snap.eps > 0 and q.current > 0:
                            q.pe_ttm = q.current / snap.eps
                        if snap.bvps and snap.bvps > 0 and q.current > 0:
                            q.pb = q.current / snap.bvps
                        if snap.total_share and q.current > 0:
                            q.total_market_cap = q.current * snap.total_share / 10000  # 万股→亿
                        if snap.circulating_share and q.current > 0:
                            q.circulating_market_cap = q.current * snap.circulating_share / 10000
                except Exception as e:
                    log_error(f"FinanceDataSource.quote_ext tdx finance error: {e}")

        if use_cache:
            self.cache.set(cache_key, q.to_dict(),
                          data_type='quote', ttl=self.CACHE_TTL['quote'])
        return q

    # ========== 逐笔成交 API ==========

    def tick_data(self, symbol: str, count: int = 800) -> Optional[List]:
        """获取逐笔成交

        Args:
            symbol: 股票代码
            count: 数量 (max 800 per call)

        Returns:
            TickData list or None
        """
        symbol = self._resolve_symbol(symbol)
        provider = self.get_provider('tdx')
        if provider and hasattr(provider, 'transaction'):
            try:
                return provider.transaction(symbol, count=count)
            except Exception as e:
                log_error(f"FinanceDataSource.tick_data error: {e}")
        return None

    def tick_data_history(self, symbol: str, date: str, count: int = 800) -> Optional[List]:
        """获取历史逐笔成交

        Args:
            symbol: 股票代码
            date: 日期 YYYYMMDD
            count: 数量

        Returns:
            TickData list or None
        """
        symbol = self._resolve_symbol(symbol)
        provider = self.get_provider('tdx')
        if provider and hasattr(provider, 'transaction_history'):
            try:
                return provider.transaction_history(symbol, date=date, count=count)
            except Exception as e:
                log_error(f"FinanceDataSource.tick_data_history error: {e}")
        return None

    # ========== 财务快照 API ==========

    def finance_snapshot(self, symbol: str) -> Optional[Dict]:
        """获取财务快照

        快速基本面数据: 流通股本/总股本/总资产/净资产/EPS/每股净资产/股东人数

        路由: tdx(mootdx finance) → tushare(financial_indicator)
        """
        symbol = self._resolve_symbol(symbol)
        cache_key = f"finance_snapshot:{symbol}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        # 优先 tdx (免费、快速)
        provider = self.get_provider('tdx')
        if provider and hasattr(provider, 'finance'):
            try:
                result = provider.finance(symbol)
                if result:
                    d = result.to_dict()
                    self.cache.set(cache_key, d, data_type='finance_snapshot', ttl=self.CACHE_TTL['finance_snapshot'])
                    return d
            except Exception as e:
                log_error(f"FinanceDataSource.finance_snapshot tdx error: {e}")

        # 回退: tushare financial_indicator
        tu = self.get_provider('tushare')
        if tu:
            try:
                ts_code = self._to_ts_code(symbol)
                indicator = tu.get_fina_indicator(ts_code=ts_code)
                if indicator and not records_empty(indicator):
                    row = indicator[0] if isinstance(indicator, list) else indicator
                    d = {
                        'symbol': symbol,
                        'source': 'tushare',
                    }
                    # 从 tushare fina_indicator 提取对应字段
                    for key, tushare_key in [
                        ('eps', 'eps'),
                        ('bvps', 'bps'),
                        ('total_share', 'total_share'),
                        ('circulating_share', 'float_share'),
                    ]:
                        val = row.get(tushare_key)
                        if val is not None:
                            d[key] = float(val) if not is_null(val) else None
                    self.cache.set(cache_key, d, data_type='finance_snapshot', ttl=self.CACHE_TTL['finance_snapshot'])
                    return d
            except Exception as e:
                log_error(f"FinanceDataSource.finance_snapshot tushare error: {e}")

        return None

    # ========== F10 数据 API ==========

    def f10(self, symbol: str, category: str = None) -> Optional[Dict]:
        """获取F10数据

        Args:
            symbol: 股票代码
            category: F10分类名称 (None=返回分类列表)

        Returns:
            {'categories': [...]} 或 {'detail': [...]} 或 None
        """
        symbol = self._resolve_symbol(symbol)
        cache_key = f"f10:{symbol}:{category or 'list'}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        provider = self.get_provider('tdx')
        if provider and hasattr(provider, 'f10_categories'):
            try:
                if category is None:
                    cats = provider.f10_categories(symbol)
                    if cats:
                        result = {'categories': cats, 'source': provider.name}
                        self.cache.set(cache_key, result, data_type='f10', ttl=self.CACHE_TTL['f10'])
                        return result
                else:
                    detail = provider.f10_detail(symbol, category)
                    if detail:
                        result = {'detail': detail, 'category': category, 'source': provider.name}
                        self.cache.set(cache_key, result, data_type='f10', ttl=self.CACHE_TTL['f10'])
                        return result
            except Exception as e:
                log_error(f"FinanceDataSource.f10 error: {e}")
        return None

    # ========== 除权除息 API ==========

    def xdxr(self, symbol: str) -> Optional[List[Dict]]:
        """获取除权除息数据

        路由: tdx(mootdx xdxr) → tushare(dividend)
        """
        symbol = self._resolve_symbol(symbol)
        cache_key = f"xdxr:{symbol}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        # 优先 tdx
        provider = self.get_provider('tdx')
        if provider and hasattr(provider, 'xdxr'):
            try:
                result = provider.xdxr(symbol)
                if result:
                    d = [x.to_dict() for x in result]
                    self.cache.set(cache_key, d, data_type='xdxr', ttl=self.CACHE_TTL['xdxr'])
                    return d
            except Exception as e:
                log_error(f"FinanceDataSource.xdxr tdx error: {e}")

        # 回退: tushare dividend
        return self.dividend(symbol)

    # ========== 研报 API ==========

    def report_list(self, symbol: str, start_date: str = None, end_date: str = None) -> Optional[List[Dict]]:
        """获取研报列表

        路由: akshare → mx_search
        """
        symbol = self._resolve_symbol(symbol)
        cache_key = f"report_list:{symbol}:{start_date}:{end_date}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        route = self.router.route(DataType.REPORT_LIST, symbol)
        for provider_name in route.providers:
            provider = self.get_provider(provider_name)
            if not provider:
                continue
            try:
                if provider_name == 'aggregate' and hasattr(provider, 'report_list'):
                    result = provider.report_list(symbol, start_date=start_date, end_date=end_date)
                    if result:
                        self.cache.set(cache_key, result, data_type='report', ttl=self.CACHE_TTL['report'])
                        return result
                elif provider_name == 'mx_search':
                    return provider.search_report(symbol)
            except Exception as e:
                log_error(f"FinanceDataSource.report_list error from {provider_name}: {e}")
                continue
        return None

    def report_forecast(self, symbol: str) -> Optional[List[Dict]]:
        """获取盈利预测/机构预期

        路由: akshare
        """
        symbol = self._resolve_symbol(symbol)
        provider = self.get_provider('aggregate')
        if provider and hasattr(provider, 'profit_forecast'):
            try:
                return provider.profit_forecast(symbol)
            except Exception as e:
                log_error(f"FinanceDataSource.report_forecast error: {e}")
        return None

    def report_rating(self, symbol: str) -> Optional[List[Dict]]:
        """获取机构评级汇总

        路由: akshare
        """
        symbol = self._resolve_symbol(symbol)
        provider = self.get_provider('aggregate')
        if provider and hasattr(provider, 'rating_summary'):
            try:
                return provider.rating_summary(symbol)
            except Exception as e:
                log_error(f"FinanceDataSource.report_rating error: {e}")
        return None

    def institution_recommend(self, symbol: str) -> Optional[List[Dict]]:
        """获取机构推荐

        路由: akshare
        """
        symbol = self._resolve_symbol(symbol)
        provider = self.get_provider('aggregate')
        if provider and hasattr(provider, 'institution_recommend'):
            try:
                return provider.institution_recommend(symbol)
            except Exception as e:
                log_error(f"FinanceDataSource.institution_recommend error: {e}")
        return None

    def institution_participation(self, symbol: str) -> Optional[Dict]:
        """获取机构参与度

        路由: akshare
        """
        symbol = self._resolve_symbol(symbol)
        provider = self.get_provider('aggregate')
        if provider and hasattr(provider, 'institution_participation'):
            try:
                return provider.institution_participation(symbol)
            except Exception as e:
                log_error(f"FinanceDataSource.institution_participation error: {e}")
        return None

    # ========== 问财 NL 查询 API ==========

    def iwencai(self, question: str, **kwargs) -> Optional[List[Dict]]:
        """自然语言选股查询 (问财)

        Args:
            question: 自然语言查询 (如 "连续3年ROE大于15%的股票")

        路由: iwencai
        """
        provider = self.get_provider('iwencai')
        if provider and hasattr(provider, 'query'):
            try:
                return provider.query(question, **kwargs)
            except Exception as e:
                log_error(f"FinanceDataSource.iwencai error: {e}")
        return None

    # ========== 公告 API ==========

    def announcement_list(
        self,
        symbol: str,
        category: str = '',
        start_date: str = None,
        end_date: str = None,
    ) -> Optional[List[Dict]]:
        """获取个股公告列表

        路由: cninfo → akshare → mx_search
        """
        symbol = self._resolve_symbol(symbol)
        cache_key = f"announcement_list:{symbol}:{category}:{start_date}:{end_date}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        route = self.router.route(DataType.ANNOUNCEMENT, symbol)
        for provider_name in route.providers:
            provider = self.get_provider(provider_name)
            if not provider:
                continue
            try:
                if provider_name == 'cninfo' and hasattr(provider, 'announcement_list'):
                    result = provider.announcement_list(symbol, category=category,
                                                        start_date=start_date, end_date=end_date)
                    if result and result.get('announcements'):
                        anns = result['announcements']
                        self.cache.set(cache_key, anns, data_type='announcement', ttl=self.CACHE_TTL['announcement'])
                        return anns
                elif provider_name == 'aggregate' and hasattr(provider, 'announcement_list'):
                    result = provider.announcement_list(symbol, category=category,
                                                        start_date=start_date, end_date=end_date)
                    if result:
                        self.cache.set(cache_key, result, data_type='announcement', ttl=self.CACHE_TTL['announcement'])
                        return result
                elif provider_name == 'mx_search':
                    return provider.search_announcement(symbol, days=30)
            except Exception as e:
                log_error(f"FinanceDataSource.announcement_list error from {provider_name}: {e}")
                continue
        return None

    def announcement_pdf_url(self, adjunct_url: str) -> Optional[str]:
        """获取公告PDF下载链接

        路由: cninfo
        """
        provider = self.get_provider('cninfo')
        if provider and hasattr(provider, 'announcement_pdf_url'):
            return provider.announcement_pdf_url(adjunct_url)
        return None

    def announcement_full_text(self, adjunct_url: str) -> Optional[str]:
        """获取公告全文 (PDF下载+文本提取)

        路由: cninfo
        """
        provider = self.get_provider('cninfo')
        if provider and hasattr(provider, 'announcement_full_text'):
            try:
                return provider.announcement_full_text(adjunct_url)
            except Exception as e:
                log_error(f"FinanceDataSource.announcement_full_text error: {e}")
        return None

    def latest_announcements(self, date: str = None, category: str = '全部') -> Optional[List[Dict]]:
        """获取全市场最新公告

        Args:
            date: YYYYMMDD (default: today)
            category: 全部/重大事项/财务报告/etc.

        路由: akshare
        """
        if date is None:
            date = datetime.now().strftime('%Y%m%d')
        provider = self.get_provider('aggregate')
        if provider and hasattr(provider, 'announcement_market'):
            try:
                return provider.announcement_market(date, category)
            except Exception as e:
                log_error(f"FinanceDataSource.latest_announcements error: {e}")
        return None

    def company_events(self, date: str = None) -> Optional[List[Dict]]:
        """获取公司动态日历

        Args:
            date: YYYYMMDD (default: today)

        路由: akshare
        """
        if date is None:
            date = datetime.now().strftime('%Y%m%d')
        provider = self.get_provider('aggregate')
        if provider and hasattr(provider, 'company_events'):
            try:
                return provider.company_events(date)
            except Exception as e:
                log_error(f"FinanceDataSource.company_events error: {e}")
        return None

    # ========== 资金流向 API ==========

    def money_flow(self, symbol: str, days: int = 30) -> Optional[List[Dict]]:
        """获取个股资金流向

        走路由器规则 (见 router.py DataType.MONEY_FLOW)，默认顺序:
            tushare → mx_data → xueqiu

        Args:
            symbol: 股票代码
            days: 返回天数

        Returns:
            资金流向数据列表（字段因数据源而异）
        """
        symbol = self._resolve_symbol(symbol)
        route = self.router.route(DataType.MONEY_FLOW, symbol)

        for provider_name in route.providers:
            provider = self.get_provider(provider_name)
            if not provider:
                continue
            if not self.rate_limiter.check(provider_name):
                continue

            try:
                start_time = time.time()
                result = None
                # Tushare provider 使用 get_money_flow；其他 provider 使用 money_flow
                if provider_name == 'tushare':
                    try:
                        result = provider.money_flow(symbol, days=days)
                    except Exception as e:
                        log_error(f"Tushare money_flow error: {e}")
                        result = None
                    # Tushare：list[dict]
                    if result is not None and isinstance(result, list) and days:
                        result = result[:days]
                elif hasattr(provider, 'money_flow'):
                    result = provider.money_flow(symbol, days=days)
                else:
                    continue

                latency = (time.time() - start_time) * 1000
                # 安全的非空检查：必须是list且不为空
                if result is not None and isinstance(result, list) and len(result) > 0:
                    self.rate_limiter.record_request(provider_name)
                    if isinstance(self.router, SmartRouter):
                        self.router.record_result(provider_name, True, latency)
                    return result

            except Exception as e:
                self.rate_limiter.record_failure(provider_name)
                if isinstance(self.router, SmartRouter):
                    self.router.record_result(provider_name, False, 0)
                log_error(f"FinanceDataSource.money_flow error from {provider_name}: {e}")
                continue

        return None

    def capital_flow(self, symbol: str) -> Optional[Dict]:
        """获取当日分钟级资金流向（雪球）

        Args:
            symbol: 股票代码
        """
        symbol = self._resolve_symbol(symbol)
        provider = self.get_provider('xueqiu')
        if provider:
            try:
                return provider.capital_flow(symbol)
            except Exception as e:
                log_error(f"FinanceDataSource.capital_flow error: {e}")
        return None

    # ========== 雪球特色 API ==========

    def cube_rebalancing(self, cube_symbol: str, count: int = 20, page: int = 1) -> Optional[Dict]:
        """获取雪球组合调仓历史

        Args:
            cube_symbol: 组合代码，如 ZH3404752
            count: 返回条数
            page: 页码
        """
        provider = self.get_provider('xueqiu')
        if provider:
            try:
                return provider.cube_rebalancing(cube_symbol, count=count, page=page)
            except Exception as e:
                log_error(f"FinanceDataSource.cube_rebalancing error: {e}")
        return None

    def cube_quote(self, symbol: str) -> Optional[Dict]:
        """获取雪球组合/股票批量报价

        Args:
            symbol: 组合或股票代码，支持批量如 "SH600519,SZ000001"
        """
        provider = self.get_provider('xueqiu')
        if provider:
            try:
                return provider.cube_quote(symbol)
            except Exception as e:
                log_error(f"FinanceDataSource.cube_quote error: {e}")
        return None

    def cube_nav(self, cube_symbol: str, days: int = 90) -> Optional[Dict]:
        """获取雪球组合净值变化

        Args:
            cube_symbol: 组合代码，如 ZH3404752
            days: 返回天数（默认90天）
        """
        provider = self.get_provider('xueqiu')
        if provider:
            try:
                import time
                until_ms = int(time.time() * 1000)
                since_ms = until_ms - days * 86400 * 1000
                return provider.cube_nav(cube_symbol, since_ms=since_ms, until_ms=until_ms)
            except Exception as e:
                log_error(f"FinanceDataSource.cube_nav error: {e}")
        return None

    def watchlist_stocks(self) -> Optional[Dict]:
        """获取雪球自选股列表

        Returns:
            自选股数据字典
        """
        provider = self.get_provider('xueqiu')
        if provider:
            try:
                return provider.watchlist_stocks()
            except Exception as e:
                log_error(f"FinanceDataSource.watchlist_stocks error: {e}")
        return None

    def index_quotes(self) -> Optional[Dict]:
        """获取大盘指数行情（上证/深证/创业板）

        Returns:
            指数行情数据字典
        """
        provider = self.get_provider('xueqiu')
        if provider:
            try:
                return provider.index_quotes()
            except Exception as e:
                log_error(f"FinanceDataSource.index_quotes error: {e}")
        return None

    def index_list(self, market: str = None):
        """获取指数列表 (Tushare)

        Args:
            market: 交易所代码 SSE/SZSE/CICC/MSCI/SW

        Returns:
            DataFrame: 指数基础信息
        """
        provider = self.get_provider('tushare')
        if provider:
            try:
                return provider.get_index_basic(market)
            except Exception as e:
                log_error(f"FinanceDataSource.index_list error: {e}")
        return None

    def index_kline(self, index_code: str, start_date: str = None, end_date: str = None):
        """获取指数K线 (Tushare)

        Args:
            index_code: 指数代码，如 000001.SH
            start_date: 开始日期 YYYYMMDD
            end_date: 结束日期 YYYYMMDD

        Returns:
            DataFrame: 指数日线数据
        """
        provider = self.get_provider('tushare')
        if provider:
            try:
                return provider.get_index_daily(index_code, start_date, end_date)
            except Exception as e:
                log_error(f"FinanceDataSource.index_kline error: {e}")
        return None

    def north_money_flow(self, start_date: str = None, end_date: str = None):
        """获取北向资金流向 (Tushare)

        Args:
            start_date: 开始日期 YYYYMMDD
            end_date: 结束日期 YYYYMMDD

        Returns:
            DataFrame: 北向资金每日流向
        """
        provider = self.get_provider('tushare')
        if provider:
            try:
                return provider.get_moneyflow_hsgt(start_date, end_date)
            except Exception as e:
                log_error(f"FinanceDataSource.north_money_flow error: {e}")
        return None

    def hsgt_top10(self, trade_date: str = None):
        """获取沪深港通十大成交股 (Tushare)

        Args:
            trade_date: 交易日期 YYYYMMDD，默认昨天

        Returns:
            DataFrame: 十大成交股数据
        """
        provider = self.get_provider('tushare')
        if provider:
            try:
                return provider.get_hsgt_top10(trade_date)
            except Exception as e:
                log_error(f"FinanceDataSource.hsgt_top10 error: {e}")
        return None

    def top_list(self, trade_date: str = None):
        """获取龙虎榜每日明细 (Tushare)

        Args:
            trade_date: 交易日期 YYYYMMDD，默认昨天

        Returns:
            DataFrame: 龙虎榜数据
        """
        provider = self.get_provider('tushare')
        if provider:
            try:
                return provider.get_top_list(trade_date)
            except Exception as e:
                log_error(f"FinanceDataSource.top_list error: {e}")
        return None

    def limit_up_down(self, trade_date: str = None):
        """获取每日涨跌停股票 (Tushare)

        Args:
            trade_date: 交易日期 YYYYMMDD，默认昨天

        Returns:
            DataFrame: 涨跌停股票列表
        """
        provider = self.get_provider('tushare')
        if provider:
            try:
                return provider.get_limit_list(trade_date)
            except Exception as e:
                log_error(f"FinanceDataSource.limit_up_down error: {e}")
        return None

    def stk_mins(self, symbol: str, start_date: str = None, end_date: str = None, freq: str = '1min'):
        """分钟线：list[dict]（每行为一根 K 线）。不使用 Tushare ``stk_mins``（需单独权限）；走 ``kline(period=freq)`` 公开源。"""
        try:
            kl = self.kline(
                symbol,
                period=freq,
                count=400,
                start_date=start_date,
                end_date=end_date,
                use_cache=True,
            )
            if not kl:
                return None
            return [k.to_dict() for k in kl]
        except Exception as e:
            log_error(f"FinanceDataSource.stk_mins error: {e}")
            return None

    def forecast(self, symbol: str, start_date: str = None, end_date: str = None):
        """获取业绩预告 (Tushare)

        Args:
            symbol: 股票代码
            start_date: 公告开始日期 YYYYMMDD
            end_date: 公告结束日期 YYYYMMDD

        Returns:
            DataFrame: 业绩预告数据
        """
        symbol = self._resolve_symbol(symbol)
        provider = self.get_provider('tushare')
        if provider:
            try:
                ts_code = provider.normalize_code(symbol)
                return provider.get_forecast(ts_code, start_date, end_date)
            except Exception as e:
                log_error(f"FinanceDataSource.forecast error: {e}")
        return None

    def express(self, symbol: str, start_date: str = None, end_date: str = None):
        """获取业绩快报 (Tushare)

        Args:
            symbol: 股票代码
            start_date: 公告开始日期 YYYYMMDD
            end_date: 公告结束日期 YYYYMMDD

        Returns:
            DataFrame: 业绩快报数据
        """
        symbol = self._resolve_symbol(symbol)
        provider = self.get_provider('tushare')
        if provider:
            try:
                ts_code = provider.normalize_code(symbol)
                return provider.get_express(ts_code, start_date, end_date)
            except Exception as e:
                log_error(f"FinanceDataSource.express error: {e}")
        return None

    def cn_cpi(self, month: str = None):
        """获取CPI数据 (Tushare)

        Args:
            month: 月份 YYYYMM，默认最近12个月

        Returns:
            DataFrame: CPI数据
        """
        provider = self.get_provider('tushare')
        if provider:
            try:
                return provider.get_cn_cpi(month)
            except Exception as e:
                log_error(f"FinanceDataSource.cn_cpi error: {e}")
        return None

    def cn_ppi(self, month: str = None):
        """获取PPI数据 (Tushare)

        Args:
            month: 月份 YYYYMM，默认最近12个月

        Returns:
            DataFrame: PPI数据
        """
        provider = self.get_provider('tushare')
        if provider:
            try:
                return provider.get_cn_ppi(month)
            except Exception as e:
                log_error(f"FinanceDataSource.cn_ppi error: {e}")
        return None

    def cn_pmi(self, month: str = None):
        """获取PMI数据 (Tushare)

        Args:
            month: 月份 YYYYMM，默认最近12个月

        Returns:
            DataFrame: PMI数据
        """
        provider = self.get_provider('tushare')
        if provider:
            try:
                return provider.get_cn_pmi(month)
            except Exception as e:
                log_error(f"FinanceDataSource.cn_pmi error: {e}")
        return None

    def cn_gdp(self, quarter: str = None):
        """获取GDP数据 (Tushare)

        Args:
            quarter: 季度 YYYYQ，默认最近8个季度

        Returns:
            DataFrame: GDP数据
        """
        provider = self.get_provider('tushare')
        if provider:
            try:
                return provider.get_cn_gdp(quarter)
            except Exception as e:
                log_error(f"FinanceDataSource.cn_gdp error: {e}")
        return None

    def cn_m(self, month: str = None):
        """获取M2/M1货币供应量数据 (Tushare)

        Args:
            month: 月份 YYYYMM，默认最近12个月

        Returns:
            DataFrame: 货币供应量数据
        """
        provider = self.get_provider('tushare')
        if provider:
            try:
                return provider.get_cn_m(month)
            except Exception as e:
                log_error(f"FinanceDataSource.cn_m error: {e}")
        return None

    def shibor(self, date: str = None):
        """获取Shibor利率数据 (Tushare)

        Args:
            date: 日期 YYYYMMDD，默认最近10个交易日

        Returns:
            DataFrame: Shibor利率数据
        """
        provider = self.get_provider('tushare')
        if provider:
            try:
                return provider.get_shibor(date)
            except Exception as e:
                log_error(f"FinanceDataSource.shibor error: {e}")
        return None

    def tushare(self, api: str, **kwargs):
        """
        Tushare 逃生舱 - 直接调用 Tushare Pro API

        当封装的方法不能满足需求时，可以直接调用底层 Tushare API
        所有 Tushare Pro 的 API 都可以通过此方法调用

        Args:
            api: API 方法名 (如 'daily', 'income', 'new_share', 'ths_daily' 等)
            **kwargs: 传递给 API 的参数

        Returns:
            list[dict] 或 None

        Examples:
            # 获取日线行情
            rows = source.tushare('daily', ts_code='600519.SH', start_date='20240101')

            # 获取利润表
            rows = source.tushare('income', ts_code='600519.SH', period='20241231')

            # 获取新股列表
            rows = source.tushare('new_share', start_date='20240101', end_date='20241231')

            # 获取同花顺概念日线
            rows = source.tushare('ths_daily', ts_code='8841415.TI')

            # 获取可转债数据
            rows = source.tushare('cb_basic', fields='ts_code,bond_short_name,stock_code')
        """
        provider = self.get_provider('tushare')
        if provider:
            try:
                return provider.pro_call(api, **kwargs)
            except Exception as e:
                log_error(f"FinanceDataSource.tushare error ({api}): {e}")
        return None

    def insider_trading(self, symbol: str) -> Optional[List[Dict]]:
        """获取高管增减持数据

        Args:
            symbol: 股票代码，如 SZ300720, SH600519

        Returns:
            list[dict] 每条记录包含: holder_name(高管姓名), holder_type(高管类型),
                        in_de(增/减), change_vol(变动数量), change_ratio(变动比例),
                        ann_date(公告日期), trade_date(交易日期) 等
        """
        symbol = self._resolve_symbol(symbol)
        ts_code = self._to_ts_code(symbol)
        provider = self.get_provider('tushare')
        if provider:
            try:
                return provider.get_insider_trading(ts_code=ts_code)
            except Exception as e:
                log_error(f"FinanceDataSource.insider_trading error: {e}")
        return None

    def top_holders(self, symbol: str) -> Optional[List[Dict]]:
        """获取十大股东数据

        Args:
            symbol: 股票代码，如 SZ300720, SH600519

        Returns:
            list[dict] 每条记录包含: ann_date(公告日期), end_date(截止日期),
                        holder_name(股东名称), hold_amount(持股数量), hold_ratio(持股比例) 等
        """
        symbol = self._resolve_symbol(symbol)
        ts_code = self._to_ts_code(symbol)
        provider = self.get_provider('tushare')
        if provider:
            try:
                return provider.get_top10_holders(ts_code=ts_code)
            except Exception as e:
                log_error(f"FinanceDataSource.top_holders error: {e}")
        return None

    def top_float_holders(self, symbol: str) -> Optional[List[Dict]]:
        """获取十大流通股东数据

        Args:
            symbol: 股票代码，如 SZ300720, SH600519

        Returns:
            list[dict] 每条记录包含: ann_date(公告日期), end_date(截止日期),
                        holder_name(股东名称), hold_amount(持股数量), hold_ratio(持股比例) 等
        """
        symbol = self._resolve_symbol(symbol)
        ts_code = self._to_ts_code(symbol)
        provider = self.get_provider('tushare')
        if provider:
            try:
                return provider.get_top10_floatholders(ts_code=ts_code)
            except Exception as e:
                log_error(f"FinanceDataSource.top_float_holders error: {e}")
        return None

    def shareholder_count(self, symbol: str) -> Optional[List[Dict]]:
        """获取股东人数/筹码分布数据

        Args:
            symbol: 股票代码，如 SZ300720, SH600519

        Returns:
            list[dict] 每条记录包含: his_low(筹码低位), his_high(筹码高位),
                        his_width(筹码宽度), cost_5pct(5%成本), cost_15pct(15%成本),
                        cost_50pct(50%成本), cost_85pct(85%成本), cost_95pct(95%成本) 等
        """
        symbol = self._resolve_symbol(symbol)
        ts_code = self._to_ts_code(symbol)
        provider = self.get_provider('tushare')
        if provider:
            try:
                return provider.get_cyq_perf(ts_code=ts_code)
            except Exception as e:
                log_error(f"FinanceDataSource.shareholder_count error: {e}")
        return None

    def managers(self, symbol: str) -> Optional[List[Dict]]:
        """获取公司高管信息

        Args:
            symbol: 股票代码，如 SZ300720, SH600519

        Returns:
            list[dict] 每条记录包含: ann_date(公告日期), name(姓名), title(职务),
                        gender(性别), resume(简历), begin_date(任职开始), end_date(任职结束) 等
        """
        symbol = self._resolve_symbol(symbol)
        ts_code = self._to_ts_code(symbol)
        provider = self.get_provider('tushare')
        if provider:
            try:
                return provider.get_managers(ts_code=ts_code)
            except Exception as e:
                log_error(f"FinanceDataSource.managers error: {e}")
        return None

    def main_business(self, symbol: str, biz_type: str = 'P') -> Optional[List[Dict]]:
        """获取主营构成数据

        Args:
            symbol: 股票代码，如 SZ300720, SH600519
            biz_type: 类型 P(按产品)/D(按地区)，默认P

        Returns:
            list[dict] 每条记录包含: end_date(截止日期), type(类型), item_name(项目名称),
                        bz_sales(营业收入), bz_profit(营业利润), bz_cost(营业成本) 等
        """
        symbol = self._resolve_symbol(symbol)
        ts_code = self._to_ts_code(symbol)
        provider = self.get_provider('tushare')
        if provider:
            try:
                return provider.get_fina_mainbz(ts_code=ts_code, type=biz_type)
            except Exception as e:
                log_error(f"FinanceDataSource.main_business error: {e}")
        return None

    def share_unlock(self, symbol: str) -> Optional[List[Dict]]:
        """获取限售解禁数据

        Args:
            symbol: 股票代码，如 SZ300720, SH600519

        Returns:
            list[dict] 每条记录包含: ann_date(公告日期), float_date(解禁日期),
                        float_share(解禁数量), float_ratio(解禁比例),
                        holder_name(持有人), share_type(股份类型) 等
        """
        symbol = self._resolve_symbol(symbol)
        ts_code = self._to_ts_code(symbol)
        provider = self.get_provider('tushare')
        if provider:
            try:
                return provider.get_share_float(ts_code=ts_code)
            except Exception as e:
                log_error(f"FinanceDataSource.share_unlock error: {e}")
        return None

    def survey_activities(self, symbol: str) -> Optional[List[Dict]]:
        """获取调研活动数据

        Args:
            symbol: 股票代码，如 SZ300720, SH600519

        Returns:
            list[dict] 每条记录包含: surv_date(调研日期), surv_place(调研地点),
                        org_name(机构名称), org_type(机构类型), description(调研内容) 等
        """
        symbol = self._resolve_symbol(symbol)
        ts_code = self._to_ts_code(symbol)
        provider = self.get_provider('tushare')
        if provider:
            try:
                return provider.get_stk_surv(ts_code=ts_code)
            except Exception as e:
                log_error(f"FinanceDataSource.survey_activities error: {e}")
        return None

    # ========== 参考数据 API ==========

    def stock_basic(self, symbol: str = None, name: str = None,
                    list_status: str = 'L'):
        """获取股票基础信息 (Tushare)

        Args:
            symbol: 股票代码（可选）。若为空则返回全市场列表。
            name: 股票名称关键词（可选）
            list_status: 上市状态 L=上市 D=退市 P=暂停

        Returns:
            DataFrame: ts_code, symbol, name, area, industry, list_date 等
        """
        if symbol:
            symbol = self._resolve_symbol(symbol)
        provider = self.get_provider('tushare')
        if not provider:
            return None
        try:
            if symbol:
                ts_code = provider.normalize_code(symbol)
                return provider.get_stock_basic(ts_code=ts_code)
            if name:
                return provider.get_stock_basic(name=name)
            return provider.pro_call('stock_basic', list_status=list_status)
        except Exception as e:
            log_error(f"FinanceDataSource.stock_basic error: {e}")
        return None

    def name_to_code(self, name: str, market: Optional[str] = None) -> Optional[str]:
        """名称（或关键词）→ 证券代码。

        优先 **腾讯 smartbox**（A/港/美）。smartbox 对同一关键词可能返回多条 **GP / GP-A**（如 A+H）；未指定 ``market`` 时取 **返回顺序中的第一条** 证券；指定 ``market`` 时取对应市场（``a_share`` / ``hk`` / ``us``）的第一条。

        失败时：仅当未指定港/美市场（或显式 A 股）且 **Tushare** 可用时，``stock_basic(name=…)`` **仅 A 股** 兜底。

        Args:
            name: 证券简称、全称或部分关键词（与腾讯搜索框一致）。
            market: 可选。``None`` / ``"auto"`` 等表示首条 GP/GP-A；``a_share`` / ``hk`` / ``us``（及 ``a`` / ``港股`` / ``美股`` 等别名）用于在多条结果中选市场。

        Returns:
            FDS 常用代码，如 ``SH600519``、``HK00700``、``AAPL``；失败为 ``None``。
        """
        q = (name or "").strip()
        if not q:
            return None
        try:
            from teakfds.providers.tencent_provider import TencentProvider

            m = TencentProvider.normalize_smartbox_market(market)
        except Exception:
            m = None
        tx = self.get_provider("tencent")
        if tx and hasattr(tx, "smartbox_resolve_stock"):
            try:
                hit = tx.smartbox_resolve_stock(q, market)
                if hit and hit.get("code"):
                    return hit["code"]
            except Exception as e:
                log_error(f"FinanceDataSource.name_to_code tencent: {e}")
        elif tx and hasattr(tx, "smartbox_first_stock"):
            try:
                hit = tx.smartbox_first_stock(q)
                if hit and hit.get("code"):
                    return hit["code"]
            except Exception as e:
                log_error(f"FinanceDataSource.name_to_code tencent: {e}")
        if m not in (None, "a_share"):
            return None
        tu = self.get_provider("tushare")
        if not tu:
            return None
        try:
            raw = tu.get_stock_basic(name=q)
            rows = coerce_tushare_table(raw)
            if not rows:
                return None
            ts = rows[0].get("ts_code")
            if not ts:
                return None
            return normalize_symbol(str(ts), "standard")
        except Exception as e:
            log_error(f"FinanceDataSource.name_to_code tushare: {e}")
        return None

    def code_to_name(self, code: str) -> Optional[str]:
        """证券代码 → 简称。

        优先 **腾讯 smartbox**（支持 A/港/美）；失败时 **仅 A 股** 可走 Tushare ``stock_basic(ts_code=…)``。

        Args:
            code: ``SH600519``、``600519``、``00700.HK`` 等；支持 ``parse_symbol_input`` 可解析的括号写法。

        Returns:
            证券简称；失败为 ``None``。
        """
        q = self._resolve_symbol((code or "").strip())
        if not q:
            return None
        tx = self.get_provider("tencent")
        if tx and hasattr(tx, "smartbox_first_stock"):
            try:
                hit = tx.smartbox_first_stock(q)
                if hit and hit.get("name"):
                    return hit["name"]
            except Exception as e:
                log_error(f"FinanceDataSource.code_to_name tencent: {e}")
        if detect_market(q) != "a_share":
            return None
        tu = self.get_provider("tushare")
        if not tu:
            return None
        try:
            ts_code = tu.normalize_code(q)
            raw = tu.get_stock_basic(ts_code=ts_code)
            rows = coerce_tushare_table(raw)
            if rows and rows[0].get("name"):
                n = rows[0].get("name")
                return str(n).strip() if n else None
        except Exception as e:
            log_error(f"FinanceDataSource.code_to_name tushare: {e}")
        return None

    def trade_cal(self, start_date: str = None, end_date: str = None,
                  exchange: str = 'SSE'):
        """获取交易日历 (Tushare)

        Args:
            start_date: 开始日期 YYYYMMDD
            end_date: 结束日期 YYYYMMDD
            exchange: 交易所 SSE/SZSE/CFFEX/SHFE/CZCE/DCE/INE

        Returns:
            DataFrame: exchange, cal_date, is_open, pretrade_date
        """
        provider = self.get_provider('tushare')
        if not provider:
            return None
        try:
            kwargs = {'exchange': exchange}
            if start_date:
                kwargs['start_date'] = start_date
            if end_date:
                kwargs['end_date'] = end_date
            return provider.pro_call('trade_cal', **kwargs)
        except Exception as e:
            log_error(f"FinanceDataSource.trade_cal error: {e}")
        return None

    def _to_ts_code(self, symbol: str) -> str:
        """FDS前缀格式 → Tushare后缀格式: SZ300720 → 300720.SZ"""
        normalized = normalize_symbol(symbol)
        # normalized 格式如 SZ300720
        if len(normalized) > 2 and normalized[:2] in ('SH', 'SZ', 'BJ'):
            return normalized[2:] + '.' + normalized[:2]
        return symbol

    def dividend(self, symbol: str):
        """获取分红送股数据 (Tushare)

        Args:
            symbol: 股票代码

        Returns:
            DataFrame: ts_code, end_date, ann_date, div_proc, stk_div, cash_div 等
        """
        symbol = self._resolve_symbol(symbol)
        provider = self.get_provider('tushare')
        if not provider:
            return None
        try:
            ts_code = provider.normalize_code(symbol)
            return provider.pro_call('dividend', ts_code=ts_code)
        except Exception as e:
            log_error(f"FinanceDataSource.dividend error: {e}")
        return None

    # ========== 估值扩展 API ==========

    def valuation_history(self, symbol: str, years: int = 10) -> Optional[Dict]:
        """获取估值历史（理杏仁 comprehensive data）

        Args:
            symbol: 股票代码
            years: 历史年限 1/3/5/10

        Returns:
            ComprehensiveData 对象（包含 stock_info / history 等字段），或 None
        """
        symbol = self._resolve_symbol(symbol)
        provider = self.get_provider('lixinger')
        if not provider or not hasattr(provider, 'get_comprehensive_data'):
            return None
        try:
            gran_map = {1: 'y1', 3: 'y3', 5: 'y5', 10: 'y10'}
            granularity = gran_map.get(int(years), 'y10')
            return provider.get_comprehensive_data(symbol, granularity=granularity)
        except Exception as e:
            log_error(f"FinanceDataSource.valuation_history error: {e}")
        return None

    @staticmethod
    def _normalize_lixinger_percentile_dict(result: Optional[Dict]) -> Optional[Dict]:
        """统一理杏仁分位接口返回字段（与 ``get-price-metrics-chart-info`` / ``allStatisticsData`` 一致）。"""
        if not result:
            return None
        return {
            "current": result.get("current"),
            "percentile": result.get("percentile"),
            "percentile_20": result.get("percentile_20"),
            "percentile_50": result.get("percentile_50"),
            "percentile_80": result.get("percentile_80"),
            "max": result.get("max"),
            "min": result.get("min"),
            "avg": result.get("avg"),
        }

    def price_metric_percentile(
        self, symbol: str, metric: str, years: int = 10
    ) -> Optional[Dict]:
        """获取单指标历史分位（理杏仁 price-metrics 接口）。

        Args:
            symbol: 股票代码
            metric: ``pe`` / ``pe_ttm`` | ``pb`` | ``ps`` / ``ps_ttm`` | ``dyr``（股息率）
            years: 5 或 10（对应 y5 / y10）

        Returns:
            ``current``, ``percentile``, ``percentile_20``/``50``/``80``, ``max``, ``min``, ``avg``
        """
        symbol = self._resolve_symbol(symbol)
        provider = self.get_provider("lixinger")
        if not provider or not hasattr(provider, "get_percentile"):
            return None
        try:
            raw = provider.get_percentile(symbol, metric=metric, years=years)
            return self._normalize_lixinger_percentile_dict(raw)
        except Exception as e:
            log_error(f"FinanceDataSource.price_metric_percentile error: {e}")
        return None

    def pe_percentile(self, symbol: str, years: int = 10) -> Optional[Dict]:
        """获取 PE-TTM 历史分位数（理杏仁 ``pe_ttm`` 指标）。"""
        return self.price_metric_percentile(symbol, "pe_ttm", years=years)

    def pb_percentile(self, symbol: str, years: int = 10) -> Optional[Dict]:
        """获取 PB 历史分位数（理杏仁 ``pb`` 指标）。"""
        return self.price_metric_percentile(symbol, "pb", years=years)

    def ps_percentile(self, symbol: str, years: int = 10) -> Optional[Dict]:
        """获取 PS-TTM 历史分位数（理杏仁 ``ps_ttm`` 指标）。"""
        return self.price_metric_percentile(symbol, "ps_ttm", years=years)

    def dyr_percentile(self, symbol: str, years: int = 10) -> Optional[Dict]:
        """获取股息率历史分位数（理杏仁 ``dyr`` 指标，当前值为百分比口径与估值接口一致）。"""
        return self.price_metric_percentile(symbol, "dyr", years=years)

    def valuation_percentiles(self, symbol: str, years: int = 10) -> Optional[Dict]:
        """一次返回 PE-TTM / PB / PS-TTM / 股息率 四套分位（仅 **一次** 理杏仁 comprehensive 请求）。

        Returns:
            ``pe_ttm``, ``pb``, ``ps_ttm``, ``dyr`` 各为与 ``price_metric_percentile`` 相同结构；
            另含 ``granularity``, ``symbol``。
        """
        symbol = self._resolve_symbol(symbol)
        provider = self.get_provider("lixinger")
        if not provider or not hasattr(provider, "get_valuation_percentiles_bundle"):
            return None
        try:
            bundle = provider.get_valuation_percentiles_bundle(symbol, years=years)
            if not bundle:
                return None
            out = {
                "symbol": bundle.get("symbol"),
                "granularity": bundle.get("granularity"),
                "pe_ttm": self._normalize_lixinger_percentile_dict(bundle.get("pe_ttm")),
                "pb": self._normalize_lixinger_percentile_dict(bundle.get("pb")),
                "ps_ttm": self._normalize_lixinger_percentile_dict(bundle.get("ps_ttm")),
                "dyr": self._normalize_lixinger_percentile_dict(bundle.get("dyr")),
            }
            return out
        except Exception as e:
            log_error(f"FinanceDataSource.valuation_percentiles error: {e}")
        return None

    @staticmethod
    def _openclaw_root() -> Path:
        """定位 OpenClaw 根目录（含 team/signals/pools）。"""
        here = Path(__file__).resolve()
        parts = here.parts
        if "skills" in parts:
            idx = parts.index("skills")
            cand = Path(*parts[:idx])
            if (cand / "team" / "signals" / "pools").is_dir():
                return cand
        home_root = Path.home() / ".openclaw"
        if (home_root / "team" / "signals" / "pools").is_dir():
            return home_root
        if "skills" in parts:
            return Path(*parts[: parts.index("skills")])
        return home_root

    @staticmethod
    def default_undervalued_pool_path() -> Path:
        return FinanceDataSource._openclaw_root() / "team" / "signals" / "pools" / "undervalued_pool.json"

    @staticmethod
    def _backup_undervalued_pool_json(target: Path) -> None:
        if not target.exists():
            return
        old = target.with_name("undervalued_pool.old.json")
        if old.exists():
            old.unlink()
        target.rename(old)

    @staticmethod
    def _screener_stock_to_candidate(stock: Any) -> Dict[str, Any]:
        pe = float(stock.pe_percentile or 0)
        pr = "P1" if pe < 0.05 else "P2"
        return {
            "code": str(stock.code or "").strip(),
            "name": str(stock.name or "").strip(),
            "industry": str(stock.industry_name or "").strip(),
            "pe_pct": float(stock.pe_percentile or 0),
            "pb_pct": float(stock.pb_percentile or 0),
            "ps_pct": float(stock.ps_percentile or 0),
            "dyr_pct": float(stock.dyr_percentile or 0),
            "status": "待分析",
            "priority": pr,
        }

    def refresh_undervalued_pool(
        self,
        *,
        output_path: Optional[Path] = None,
        pe_percentile_max: float = 0.20,
        pb_percentile_max: float = 0.20,
        ps_percentile_max: float = 0.20,
        dyr_percentile_min: float = 0.80,
        page_size: int = 200,
        page_index_cn: int = 0,
        page_index_hk: int = 0,
        backup_existing: bool = True,
        top_n: int = 30,
    ) -> Optional[Dict[str, Any]]:
        """
        调用理杏仁 screener 刷新 A 股 / 港股低估池，并写入 team/signals/pools/undervalued_pool.json。

        与历史文件结构兼容：version、pools、filter_params、status_counts、next_actions。
        """
        provider = self.get_provider("lixinger")
        if not provider or not hasattr(provider, "screen_undervalued_stocks"):
            print("FinanceDataSource.refresh_undervalued_pool: lixinger provider unavailable")
            return None

        cn_kw: Dict[str, Any] = dict(
            area_code="cn",
            pe_percentile_max=pe_percentile_max,
            pb_percentile_max=pb_percentile_max,
            ps_percentile_max=ps_percentile_max,
            dyr_percentile_min=dyr_percentile_min,
            page_size=page_size,
            page_index=page_index_cn,
        )
        hk_kw: Dict[str, Any] = {**cn_kw, "area_code": "hk", "page_index": page_index_hk}

        try:
            cn_res = provider.screen_undervalued_stocks(**cn_kw)
            hk_res = provider.screen_undervalued_stocks(**hk_kw)
        except Exception as e:
            log_error(f"FinanceDataSource.refresh_undervalued_pool error: {e}")
            return None

        cn_tz = timezone(timedelta(hours=8))
        now = datetime.now(cn_tz)
        now_s = now.isoformat()

        def _pool_block(res: Any, label: str) -> Dict[str, Any]:
            if res is None:
                return {
                    "total": 0,
                    "last_refresh": now_s,
                    "analyzed": 0,
                    "pending": 0,
                    "top_candidates": [],
                    "error": f"{label} screener returned None",
                }
            stocks = list(res.stocks or [])
            cands = [self._screener_stock_to_candidate(s) for s in stocks]
            cands.sort(key=lambda x: x.get("pe_pct", 1.0))
            top = cands[: max(1, int(top_n))]
            total = int(res.total or 0)
            return {
                "total": total,
                "last_refresh": now_s,
                "analyzed": 0,
                "pending": total,
                "top_candidates": top,
            }

        pools = {
            "A股低估池": _pool_block(cn_res, "A股"),
            "港股低估池": _pool_block(hk_res, "港股"),
        }

        cn_total = pools["A股低估池"]["total"]
        hk_total = pools["港股低估池"]["total"]
        pending_all = int(cn_total + hk_total)

        all_top = []
        for blk in pools.values():
            all_top.extend(blk.get("top_candidates") or [])
        all_top.sort(key=lambda x: x.get("pe_pct", 1.0))

        next_actions: List[Dict[str, Any]] = []
        for c in all_top[:8]:
            pe = c.get("pe_pct", 0) or 0
            next_actions.append(
                {
                    "code": c.get("code"),
                    "action": "优先分析",
                    "reason": f"PE分位{pe * 100:.2f}%极低" if pe is not None else "低估值分位",
                    "priority": c.get("priority") or "P2",
                }
            )

        doc: Dict[str, Any] = {
            "version": "1.1",
            "updated_at": now_s,
            "source": "lixinger_api:https://www.lixinger.com/api/company/screener",
            "filter_params": {
                "pe_percentile_max": pe_percentile_max,
                "pb_percentile_max": pb_percentile_max,
                "ps_percentile_max": ps_percentile_max,
                "dyr_percentile_min": dyr_percentile_min,
                "page_size": page_size,
                "page_index_cn": page_index_cn,
                "page_index_hk": page_index_hk,
            },
            "pools": pools,
            "status_counts": {
                "已分析": 0,
                "待分析": pending_all,
                "总计": pending_all,
            },
            "next_actions": next_actions,
        }

        out = Path(output_path) if output_path else self.default_undervalued_pool_path()
        out.parent.mkdir(parents=True, exist_ok=True)
        if backup_existing:
            self._backup_undervalued_pool_json(out)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        return doc

    # ========== 补充数据源 API (V2) ==========

    def hot_stocks(self, trade_date: str = None) -> Optional[List[Dict]]:
        """当日强势股 + 题材归因（同花顺）

        Args:
            trade_date: YYYY-MM-DD, None=今天

        Returns:
            [{code, name, reason, close, change_pct, turnover_pct, amount, ...}]
        """
        provider = self.get_provider('ths')
        if provider:
            try:
                return provider.hot_stocks(trade_date)
            except Exception as e:
                log_error(f"FinanceDataSource.hot_stocks error: {e}")
        return None

    def concept_blocks(self, symbol: str) -> Optional[Dict]:
        """个股所属概念/行业/地域板块（百度 → Tushare concept_detail）

        Returns:
            {industry: [...], concept: [...], region: [...], concept_tags: [str, ...]}
        """
        symbol = self._resolve_symbol(symbol)
        provider = self.get_provider('baidu')
        if provider:
            try:
                result = provider.concept_blocks(symbol)
                if result and (
                    result.get("industry") or result.get("concept") or result.get("concept_tags")
                ):
                    return result
            except Exception as e:
                log_error(f"FinanceDataSource.concept_blocks error: {e}")
        try:
            from teakfds.integrations.tushare_concept import fetch_concept_blocks_tushare

            return fetch_concept_blocks_tushare(symbol, self.tushare)
        except Exception as e:
            log_error(f"FinanceDataSource.concept_blocks tushare fallback: {e}")
        return None

    def daily_dragon_tiger(self, trade_date: str = None, min_net_buy: float = None) -> Optional[Dict]:
        """全市场龙虎榜（东财 datacenter）

        Args:
            trade_date: YYYY-MM-DD
            min_net_buy: 净买入下限（万元）

        Returns:
            {date, total_records, stocks: [{code, name, reason, net_buy_wan, ...}]}
        """
        provider = self.get_provider('eastmoney')
        if provider:
            try:
                return provider.daily_dragon_tiger(trade_date, min_net_buy)
            except Exception as e:
                log_error(f"FinanceDataSource.daily_dragon_tiger error: {e}")
        return None

    def industry_comparison(self, top_n: int = 20) -> Optional[Dict]:
        """全行业涨跌幅排名（东财行业板块 push2）

        Returns:
            {top: [...], bottom: [...], total: int}
        """
        provider = self.get_provider('aggregate')
        if provider:
            try:
                return provider.industry_comparison(top_n)
            except Exception as e:
                log_error(f"FinanceDataSource.industry_comparison error: {e}")
        return None

    def north_money_realtime(self) -> Optional[List[Dict]]:
        """北向资金实时分钟流向（同花顺 hsgtApi）

        Returns:
            [{time, hgt_yi, sgt_yi}, ...] 单位亿元
        """
        provider = self.get_provider('ths')
        if provider:
            try:
                return provider.north_money_realtime()
            except Exception as e:
                log_error(f"FinanceDataSource.north_money_realtime error: {e}")
        return None

    def consensus_eps(self, symbol: str) -> Optional[List[Dict]]:
        """机构一致预期 EPS（同花顺/东财内部实现）

        Returns:
            [{year, count, min, mean, max}, ...]
        """
        symbol = self._resolve_symbol(symbol)
        provider = self.get_provider('aggregate')
        if provider:
            try:
                return provider.consensus_eps(symbol)
            except Exception as e:
                log_error(f"FinanceDataSource.consensus_eps error: {e}")
        return None

    def fund_flow_baidu(self, symbol: str, days: int = 20) -> Optional[List[Dict]]:
        """个股资金流向（百度股市通，money_flow 备选源）

        Returns:
            [{date, close, change_pct, superNetIn, largeNetIn, mainIn, ...}]
        """
        symbol = self._resolve_symbol(symbol)
        provider = self.get_provider('baidu')
        if provider:
            try:
                return provider.fund_flow_history(symbol, days)
            except Exception as e:
                log_error(f"FinanceDataSource.fund_flow_baidu error: {e}")
        return None

    def eastmoney_reports(self, symbol: str, max_pages: int = 3) -> Optional[List[Dict]]:
        """东财研报列表 + PDF链接（report_list 备选源）

        Returns:
            [{title, publish_date, org_name, pdf_url, eps_this_year, rating, ...}]
        """
        symbol = self._resolve_symbol(symbol)
        provider = self.get_provider('eastmoney')
        if provider:
            try:
                return provider.report_list(symbol, max_pages)
            except Exception as e:
                log_error(f"FinanceDataSource.eastmoney_reports error: {e}")
        return None

    def valuation_calc(self, symbol: str) -> Optional[Dict]:
        """完整估值分析（前向PE + PEG + PE消化时间）

        Returns:
            {name, price, pe_ttm, pb, eps_cur, eps_next, pe_fwd, cagr_pct, peg, digest_years, analyst_count}
        """
        from teakfds.valuation_utils import full_valuation
        symbol = self._resolve_symbol(symbol)
        try:
            return full_valuation(self, symbol)
        except Exception as e:
            log_error(f"FinanceDataSource.valuation_calc error: {e}")
            return None

    # ========== 工具方法 ==========
    
    def get_status(self) -> Dict[str, any]:
        """获取系统状态"""
        # 获取所有已知的 provider 名称
        all_names = set(self._providers.keys())
        if hasattr(self, '_provider_factories'):
            all_names.update(self._provider_factories.keys())
        
        return {
            'providers': {
                name: self._is_provider_available(name)
                for name in all_names
            },
            'cache': self.cache.get_stats(),
            'rate_limiter': {
                name: self.rate_limiter.get_status(name)
                for name in self._providers.keys()
            }
        }
    
    def _is_provider_available(self, name: str) -> bool:
        """检查 Provider 可用性（不触发延迟加载）"""
        if name in self._providers:
            return self._providers[name].is_available()
        # 未加载的 provider，假设可用但不触发实例化
        return True
    
    def clear_cache(self):
        """清空缓存"""
        self.cache.clear()
    
    def health_check(self) -> Dict[str, bool]:
        """健康检查"""
        results = {}
        for name, provider in self._providers.items():
            results[name] = provider.is_available()
        return results

    def market_breadth(self, trade_date: str = None) -> Optional[Dict]:
        """获取市场广度数据（涨跌家数、涨跌停等）
        
        Args:
            trade_date: 交易日期 YYYYMMDD，默认最新
            
        Returns:
            dict: {trade_date, total, up, down, flat, up_limit, down_limit, 
                   advance_decline_ratio, up_pct, ...}
        """
        try:
            params = {}
            if trade_date:
                params['trade_date'] = trade_date
            data = self.tushare('daily', **params)
            if not data:
                return None
            
            total = len(data)
            up = sum(1 for d in data if float(d.get('pct_chg', 0)) > 0)
            down = sum(1 for d in data if float(d.get('pct_chg', 0)) < 0)
            flat = total - up - down
            up_limit = sum(1 for d in data if float(d.get('pct_chg', 0)) >= 9.9)
            down_limit = sum(1 for d in data if float(d.get('pct_chg', 0)) <= -9.9)
            
            # 涨跌比率
            adr = up / down if down > 0 else 99.0
            
            return {
                'trade_date': data[0].get('trade_date', '') if data else '',
                'total': total,
                'up': up,
                'down': down,
                'flat': flat,
                'up_limit': up_limit,
                'down_limit': down_limit,
                'advance_decline_ratio': round(adr, 2),
                'up_pct': round(up / total * 100, 1) if total > 0 else 0,
            }
        except Exception as e:
            print(f"market_breadth error: {e}")
            return None


# 全局实例
_financedatasource: Optional[FinanceDataSource] = None


def get_finance_data_source() -> FinanceDataSource:
    """获取全局FinanceDataSource"""
    global _financedatasource
    if _financedatasource is None:
        _financedatasource = FinanceDataSource()
    return _financedatasource


# 兼容性别名
DataProxy = FinanceDataSource

# Agent skill 主入口别名
TeakFDS = FinanceDataSource


def get_dataproxy() -> FinanceDataSource:
    """兼容性别名"""
    return get_finance_data_source()


# 便捷导出
def quote(symbol: str) -> Optional[QuoteData]:
    """便捷方法: 获取实时行情"""
    return get_finance_data_source().quote(symbol)


def kline(symbol: str, period: str = 'day', count: int = 30, adj: Optional[str] = None) -> Optional[List[KlineData]]:
    """便捷方法: 获取K线（adj 同 FinanceDataSource.kline）"""
    return get_finance_data_source().kline(symbol, period, count, adj=adj)


def valuation(symbol: str) -> Optional[ValuationData]:
    """便捷方法: 获取估值"""
    return get_finance_data_source().valuation(symbol)


def valuation_percentiles(symbol: str, years: int = 10) -> Optional[Dict]:
    """便捷方法: 一次获取 PE/PB/PS/股息率 分位（理杏仁）"""
    return get_finance_data_source().valuation_percentiles(symbol, years=years)


def name_to_code(name: str, market: Optional[str] = None) -> Optional[str]:
    """便捷方法: 名称 → 代码（可选 ``market``：``a_share`` / ``hk`` / ``us`` 等，见 ``FinanceDataSource.name_to_code``）"""
    return get_finance_data_source().name_to_code(name, market=market)


def code_to_name(code: str) -> Optional[str]:
    """便捷方法: 代码 → 名称"""
    return get_finance_data_source().code_to_name(code)


def search(query: str) -> Optional[List[Dict]]:
    """便捷方法: 金融搜索"""
    return get_finance_data_source().search(query)


if __name__ == '__main__':
    print("=" * 60)
    print("Testing FinanceDataSource v2.5")
    print("=" * 60)
    
    source = FinanceDataSource()
    
    # 打印状态
    print("\n✓ System Status:")
    status = source.get_status()
    print(f"  Providers: {status['providers']}")
    print(f"  Cache: {status['cache']}")
    
    # 测试实时行情
    print("\n✓ Testing quote:")
    quote = source.quote('SH600519')
    if quote:
        print(f"  SH600519: {quote.name} @ {quote.current:.2f} ({quote.percent:+.2f}%) from {quote.source}")
    
    # 测试K线
    print("\n✓ Testing kline:")
    klines = source.kline('SH600519', period='day', count=5)
    if klines:
        for k in klines[-3:]:
            print(f"  {k.date}: O={k.open:.2f} H={k.high:.2f} L={k.low:.2f} C={k.close:.2f}")
    
    # 测试估值
    print("\n✓ Testing valuation:")
    val = source.valuation('SH600519')
    if val:
        print(f"  PE-TTM: {val.pe_ttm}, PB: {val.pb}")

    # 测试新的Tushare方法
    print("\n✓ Testing new Tushare methods:")

    # stk_mins
    print("\n  Testing stk_mins()...")
    try:
        df = source.stk_mins('SH600519', freq='5min')
        if df is not None:
            print(f"    ✓ stk_mins: Got {len(df)} rows")
        else:
            print("    ○ stk_mins: No data (expected if market closed)")
    except Exception as e:
        print(f"    ○ stk_mins error: {e}")

    # forecast
    print("\n  Testing forecast()...")
    try:
        df = source.forecast('SH600519')
        if df is not None and not df.empty:
            print(f"    ✓ forecast: Got {len(df)} rows")
        else:
            print("    ○ forecast: No data")
    except Exception as e:
        print(f"    ○ forecast error: {e}")

    # express
    print("\n  Testing express()...")
    try:
        df = source.express('SH600519')
        if df is not None and not df.empty:
            print(f"    ✓ express: Got {len(df)} rows")
        else:
            print("    ○ express: No data")
    except Exception as e:
        print(f"    ○ express error: {e}")

    # macro data
    print("\n  Testing macro data methods...")
    try:
        df = source.cn_cpi()
        if df is not None:
            print(f"    ✓ cn_cpi: Got {len(df)} rows")
    except Exception as e:
        print(f"    ○ cn_cpi error: {e}")

    try:
        df = source.cn_ppi()
        if df is not None:
            print(f"    ✓ cn_ppi: Got {len(df)} rows")
    except Exception as e:
        print(f"    ○ cn_ppi error: {e}")

    try:
        df = source.cn_pmi()
        if df is not None:
            print(f"    ✓ cn_pmi: Got {len(df)} rows")
    except Exception as e:
        print(f"    ○ cn_pmi error: {e}")

    print("\n" + "=" * 60)
    print("✓ FinanceDataSource v2.4 test completed!")
    print("=" * 60)
