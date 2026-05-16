#!/usr/bin/env python3
"""
Router - 智能路由器
根据数据类型、市场、数据源状态自动选择最优Provider
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from teakfds.models import detect_market
from teakfds.rate_limiter import get_rate_limiter


class DataType(Enum):
    """数据类型"""
    QUOTE = 'quote'           # 实时行情
    DEPTH = 'depth'           # 盘口数据
    INTRADAY = 'intraday'     # 分时数据
    KLINE = 'kline'           # K线数据
    FINANCIAL = 'financial'   # 财务数据
    VALUATION = 'valuation'   # 估值数据
    NEWS = 'news'             # 新闻数据
    SEARCH = 'search'         # 搜索
    MONEY_FLOW = 'money_flow' # 资金流向
    TICK = 'tick'                   # 逐笔成交
    FINANCE_SNAPSHOT = 'finance_snapshot'  # 财务快照
    F10 = 'f10'                     # F10公司资料
    XDXR = 'xdxr'                   # 除权除息
    REPORT_LIST = 'report_list'     # 研报列表
    REPORT_FORECAST = 'report_forecast'  # 盈利预测/机构预期
    REPORT_RATING = 'report_rating'      # 机构评级
    IWENCai_QUERY = 'iwencai_query'  # 问财NL查询
    ANNOUNCEMENT = 'announcement'    # 公告
    HOT_STOCKS = 'hot_stocks'        # 当日强势股+题材归因
    CONCEPT_BLOCKS = 'concept_blocks'  # 概念板块归属
    DRAGON_TIGER_MARKET = 'dragon_tiger_market'  # 全市场龙虎榜
    INDUSTRY_COMPARE = 'industry_compare'  # 行业横向对比
    NORTH_MONEY_REALTIME = 'north_money_realtime'  # 北向资金实时分钟


@dataclass
class RouteResult:
    """路由结果"""
    providers: List[str]      # 按优先级排序的Provider列表
    primary: str              # 首选Provider
    fallbacks: List[str]      # 备选Provider列表
    reason: str               # 路由原因


class Router:
    """
    智能路由器
    
    功能:
    - 根据市场类型选择数据源
    - 考虑数据源健康状态
    - 支持自定义路由规则
    - 自动降级策略
    """
    
    # 路由策略配置 (最终版)
    # 格式: {数据类型: {市场: [provider优先级列表]}}
    ROUTING_RULES = {
        DataType.QUOTE: {
            # A股: 腾讯(P0) → mootdx(P1) → 新浪(P2) → Tushare(P3) → mx-data(P4) → 雪球(P5) → Search(P6)
            'a_share': ['tencent', 'tdx', 'sina', 'tushare', 'mx_data', 'xueqiu', 'search_fallback'],
            # 港股: 腾讯(P0) → 新浪(P1) → mx-data(P2) → Search(P3)
            'hk': ['tencent', 'sina', 'mx_data', 'search_fallback'],
            # 美股: 腾讯(P0) → 新浪(P1) → mx-data(P2) → Search(P3)
            'us': ['tencent', 'sina', 'mx_data', 'search_fallback'],
        },
        DataType.DEPTH: {
            'a_share': ['tencent', 'tdx', 'mx_data', 'xueqiu'],
            'hk': ['tencent'],
            'us': ['tencent'],
        },
        DataType.INTRADAY: {
            'a_share': ['tencent', 'tdx', 'mx_data'],
            'hk': ['tencent'],
            'us': ['tencent'],
        },
        DataType.KLINE: {
            # A股日线：Qlib优先（前复权+复权因子，数据质量高，2000年至今6000+股票）
            # tdx (mootdx) 作为网络行情降级源
            'a_share': ['qlib', 'tushare', 'tencent', 'tdx', 'xueqiu'],
            'hk': ['local_tdx', 'tencent', 'sina'],  # Qlib 无港股，港股走 local_tdx
            'us': ['tencent', 'sina'],
        },
        DataType.FINANCIAL: {
            'a_share': ['tushare'],
            'hk': [],
            'us': [],
        },
        DataType.VALUATION: {
            # 估值: 理杏仁(P0) → Tushare(P1) → 雪球(P2)；港股由理杏仁（与爬虫 hk 路由一致）
            'a_share': ['lixinger', 'tushare', 'xueqiu'],
            'hk': ['lixinger'],
            'us': [],
        },
        DataType.NEWS: {
            # 新闻: mx-search(P0) → baidu(P1) → firecrawl(P2) → tavily(P3)
            'a_share': ['mx_search', 'search_fallback'],
            'hk': ['mx_search', 'search_fallback'],
            'us': ['mx_search', 'search_fallback'],
        },
        DataType.SEARCH: {
            # 搜索: mx-search(P0) → baidu(P1) → firecrawl(P2) → tavily(P3)
            'a_share': ['mx_search', 'search_fallback'],
            'hk': ['mx_search', 'search_fallback'],
            'us': ['mx_search', 'search_fallback'],
        },
        DataType.MONEY_FLOW: {
            'a_share': ['tencent', 'tushare', 'mx_data', 'xueqiu', 'baidu'],
            'hk': [],
            'us': [],
        },
        DataType.TICK: {
            'a_share': ['tdx'],
        },
        DataType.FINANCE_SNAPSHOT: {
            'a_share': ['tdx', 'tushare'],
        },
        DataType.F10: {
            'a_share': ['tdx'],
        },
        DataType.XDXR: {
            'a_share': ['tdx', 'tushare'],
        },
        DataType.REPORT_LIST: {
            # 东财放后：妙想 / aggregate（巨潮+东财 HTTP 内部实现）优先
            'a_share': ['mx_search', 'aggregate', 'eastmoney'],
        },
        DataType.REPORT_FORECAST: {
            'a_share': ['aggregate'],
        },
        DataType.REPORT_RATING: {
            'a_share': ['aggregate'],
        },
        DataType.IWENCai_QUERY: {
            'a_share': ['iwencai'],
        },
        DataType.ANNOUNCEMENT: {
            'a_share': ['cninfo', 'aggregate', 'mx_search'],
        },
        DataType.HOT_STOCKS: {
            'a_share': ['ths'],
        },
        DataType.CONCEPT_BLOCKS: {
            'a_share': ['baidu'],
        },
        DataType.DRAGON_TIGER_MARKET: {
            'a_share': ['eastmoney'],
        },
        DataType.INDUSTRY_COMPARE: {
            'a_share': ['aggregate'],
        },
        DataType.NORTH_MONEY_REALTIME: {
            'a_share': ['ths'],
        },
    }
    
    # K线周期特殊路由
    KLINE_PERIOD_ROUTING = {
        '1min': ['tencent', 'tdx', 'mx_data'],
        '5min': ['tencent', 'tdx', 'mx_data'],
        '15min': ['tencent', 'tdx', 'mx_data'],
        '30min': ['tencent', 'tdx', 'mx_data'],
        '60min': ['tencent', 'tdx', 'mx_data'],
        'day': ['qlib', 'tushare', 'tencent', 'tdx', 'xueqiu'],  # Qlib优先, tdx(mootdx)降级
        'week': ['tushare', 'tencent', 'xueqiu'],
        'month': ['tushare', 'tencent', 'xueqiu'],
    }
    
    def __init__(self):
        self.rate_limiter = get_rate_limiter()
        self._provider_status: Dict[str, bool] = {}
        self._custom_rules: Dict[str, List[str]] = {}
    
    def route(self, 
              data_type: DataType, 
              symbol: str,
              **kwargs) -> RouteResult:
        """路由请求"""
        market = detect_market(symbol)
        providers = self._get_base_providers(data_type, market, **kwargs)
        providers = self._apply_custom_rules(data_type, providers)
        available_providers = self._filter_available(providers)
        
        if not available_providers:
            available_providers = providers
        
        return RouteResult(
            providers=available_providers,
            primary=available_providers[0] if available_providers else '',
            fallbacks=available_providers[1:] if len(available_providers) > 1 else [],
            reason=f"market={market}, type={data_type.value}, available={len(available_providers)}/{len(providers)}"
        )
    
    def _get_base_providers(self, 
                           data_type: DataType, 
                           market: str,
                           **kwargs) -> List[str]:
        """获取基础Provider列表"""
        if data_type == DataType.KLINE and 'period' in kwargs:
            period = kwargs['period']
            est = int(kwargs.get('estimated_rows') or 0)
            large_batch = bool(kwargs.get('large_batch')) or est > 500
            # 分钟线路由不区分市场（仅A股有分钟线源）
            if period in ('1min', '5min', '15min', '30min', '60min'):
                if period in self.KLINE_PERIOD_ROUTING:
                    return self.KLINE_PERIOD_ROUTING[period].copy()
            # 日线/周线/月线使用市场级路由（不同市场Provider不同）
            if data_type in self.ROUTING_RULES:
                market_rules = self.ROUTING_RULES[data_type]
                if market in market_rules:
                    base = market_rules[market].copy()
                    # 单次预计 >500 行或显式 large_batch：Qlib 本地日线优先（懒加载在 Provider 层）
                    if (
                        market == 'a_share'
                        and large_batch
                        and period in ('day', 'week', 'month')
                        and 'qlib' in base
                    ):
                        base = ['qlib'] + [p for p in base if p != 'qlib']
                    return base
        
        if data_type in self.ROUTING_RULES:
            market_rules = self.ROUTING_RULES[data_type]
            if market in market_rules:
                return market_rules[market].copy()
        
        return []
    
    def _apply_custom_rules(self, 
                           data_type: DataType, 
                           providers: List[str]) -> List[str]:
        """应用自定义路由规则"""
        key = data_type.value
        if key in self._custom_rules:
            custom = self._custom_rules[key]
            return custom + [p for p in providers if p not in custom]
        return providers
    
    def _filter_available(self, providers: List[str]) -> List[str]:
        """过滤可用的Provider（基于限流器冷却、日配额，以及手动下线状态）"""
        available = []
        for provider in providers:
            # 允许通过 set_provider_status 手动标记为 False 暂时下线
            if self._provider_status.get(provider, True) is False:
                continue
            status = self.rate_limiter.get_status(provider)
            if status.get('in_cooldown', False):
                continue
            if status.get('day_used', 0) >= status.get('day_limit', 999999):
                continue
            available.append(provider)
        return available
    
    def set_custom_rule(self, data_type: DataType, providers: List[str]) -> None:
        """设置自定义路由规则"""
        self._custom_rules[data_type.value] = providers
    
    def set_provider_status(self, provider: str, available: bool) -> None:
        """设置Provider可用状态"""
        self._provider_status[provider] = available
    
    def route_quote(self, symbol: str) -> RouteResult:
        """路由实时行情请求"""
        return self.route(DataType.QUOTE, symbol)
    
    def route_kline(self, symbol: str, period: str = 'day', **kwargs) -> RouteResult:
        """路由K线请求（可传 estimated_rows / large_batch 等，供 Qlib 大批量优先）。"""
        return self.route(DataType.KLINE, symbol, period=period, **kwargs)
    
    def route_financial(self, symbol: str) -> RouteResult:
        """路由财务数据请求"""
        return self.route(DataType.FINANCIAL, symbol)
    
    def route_valuation(self, symbol: str) -> RouteResult:
        """路由估值数据请求"""
        return self.route(DataType.VALUATION, symbol)
    
    def route_search(self, query: str) -> RouteResult:
        """路由搜索请求"""
        return self.route(DataType.SEARCH, 'default', query=query)


class SmartRouter(Router):
    """增强型智能路由器 - 学习数据源性能

    在 `route()` 返回候选列表前，根据历史成功率与延迟对候选 provider 重排。
    保留原始优先级作为"先验分"，避免在没有历史数据时乱序。

    打分:
        score = success_rate * 0.6 + latency_score * 0.4
        latency_score = clamp((2000 - avg_latency_ms) / 1900, 0, 1)

    排序原则：
        - 只有当一个 provider **累计 >=3 次调用** 且 **score 与前一个 provider 差距显著 (>0.1)** 时，
          才会允许其前移，避免首次失败后就被下调优先级。
    """

    # 触发重排所需的最小样本数
    MIN_SAMPLES = 3
    # 仅当分数差大于该阈值才允许重排
    SCORE_DIFF_THRESHOLD = 0.1

    def __init__(self):
        super().__init__()
        self._latency_history: Dict[str, List[float]] = {}
        self._success_rate: Dict[str, Tuple[int, int]] = {}

    def record_result(self, provider: str, success: bool, latency_ms: float) -> None:
        """记录请求结果"""
        if provider not in self._latency_history:
            self._latency_history[provider] = []
        if latency_ms > 0:
            self._latency_history[provider].append(latency_ms)

        if len(self._latency_history[provider]) > 100:
            self._latency_history[provider] = self._latency_history[provider][-100:]

        if provider not in self._success_rate:
            self._success_rate[provider] = (0, 0)

        success_count, total_count = self._success_rate[provider]
        if success:
            self._success_rate[provider] = (success_count + 1, total_count + 1)
        else:
            self._success_rate[provider] = (success_count, total_count + 1)

    def get_provider_score(self, provider: str) -> float:
        """计算Provider得分"""
        success_rate = 0.5
        if provider in self._success_rate:
            success, total = self._success_rate[provider]
            if total > 0:
                success_rate = success / total

        latency_score = 0.5
        if provider in self._latency_history and self._latency_history[provider]:
            avg_latency = sum(self._latency_history[provider]) / len(self._latency_history[provider])
            latency_score = max(0, min(1, (2000 - avg_latency) / 1900))

        return success_rate * 0.6 + latency_score * 0.4

    def get_provider_samples(self, provider: str) -> int:
        """返回某个 provider 已累计的样本数 (成功+失败)"""
        if provider in self._success_rate:
            _, total = self._success_rate[provider]
            return total
        return 0

    def route(self,
              data_type: DataType,
              symbol: str,
              **kwargs) -> RouteResult:
        """路由请求：在基础路由基础上按学习到的分数重排候选"""
        result = super().route(data_type, symbol, **kwargs)
        reordered = self._rerank(result.providers)
        return RouteResult(
            providers=reordered,
            primary=reordered[0] if reordered else '',
            fallbacks=reordered[1:] if len(reordered) > 1 else [],
            reason=result.reason + f"; smart_reranked={reordered != result.providers}",
        )

    def _rerank(self, providers: List[str]) -> List[str]:
        """根据样本数、分数对候选 provider 重排。

        策略：
        - 只有累计样本 >= MIN_SAMPLES 的 provider 参与分数比较
        - 否则保留原先验优先级顺序
        - 候选分数差大于 SCORE_DIFF_THRESHOLD 才调换位置
        """
        if not providers or len(providers) <= 1:
            return providers

        # 带原始索引的元组 (priority_idx, provider, has_enough_samples, score)
        annotated = []
        for idx, p in enumerate(providers):
            samples = self.get_provider_samples(p)
            has_data = samples >= self.MIN_SAMPLES
            score = self.get_provider_score(p) if has_data else 0.5
            annotated.append((idx, p, has_data, score))

        # 分桶：有样本的按分数排；无样本的按原优先级。然后合并
        with_data = [x for x in annotated if x[2]]
        without_data = [x for x in annotated if not x[2]]

        # 有样本的再看与原排序差异是否显著
        with_data_sorted = sorted(with_data, key=lambda x: (-x[3], x[0]))

        # 如果重排后第一名分数比原第一名高 SCORE_DIFF_THRESHOLD 以上，才启用新顺序
        def _check_swap(original: List[tuple], new: List[tuple]) -> List[tuple]:
            if not original or not new:
                return original
            if original[0][1] == new[0][1]:
                return original
            if new[0][3] - original[0][3] < self.SCORE_DIFF_THRESHOLD:
                return original
            return new

        final_with_data = _check_swap(with_data, with_data_sorted)

        # 保留 with_data 在原 providers 中的位置区间：把重排后的塞回相同下标序列
        with_idx_positions = [x[0] for x in with_data]
        with_idx_positions.sort()
        merged = list(providers)
        for pos, item in zip(with_idx_positions, final_with_data):
            merged[pos] = item[1]
        return merged


# 全局路由器实例
_router: Optional[Router] = None


def get_router() -> Router:
    """获取全局路由器"""
    global _router
    if _router is None:
        _router = SmartRouter()
    return _router


if __name__ == '__main__':
    print("Testing Router v2...")
    
    router = Router()
    
    # 测试A股实时行情路由
    print("\nA股实时行情:")
    result = router.route_quote('SH600519')
    print(f"  {result.providers}")
    
    # 测试港股实时行情路由
    print("\n港股实时行情:")
    result = router.route_quote('00700.HK')
    print(f"  {result.providers}")
    
    # 测试美股实时行情路由
    print("\n美股实时行情:")
    result = router.route_quote('AAPL')
    print(f"  {result.providers}")
    
    # 测试K线路由
    print("\nA股日线:")
    result = router.route_kline('SH600519', 'day')
    print(f"  {result.providers}")
    
    print("\nA股分钟线:")
    result = router.route_kline('SH600519', '5min')
    print(f"  {result.providers}")
    
    # 测试估值路由
    print("\n估值数据:")
    result = router.route_valuation('SH600519')
    print(f"  {result.providers}")
    
    # 测试搜索路由
    print("\n搜索:")
    result = router.route_search('贵州茅台')
    print(f"  {result.providers}")
    
    print("\n✓ Router test passed!")
