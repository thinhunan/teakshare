#!/usr/bin/env python3
"""
DataProxy 统一数据模型
所有数据源返回统一格式的数据结构
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
import re


# ========== 指数代码集合 ==========
# 上交所指数：000xxx（如 000300 沪深300, 000016 上证50, 000905 中证500）
# 深交所指数：399xxx（如 399001 深证成指, 399006 创业板指, 399673 创业板50）
# 注意：000xxx 既是上交所指数代码段，也是深交所股票代码段（如 000001 平安银行）
# 因此指数代码需要优先判断，否则会被误归类为深交所股票

# 已知上交所指数代码（6位纯数字，不含前缀）
SHINDEX_CODES_6D = {
    "000001",  # 上证指数
    "000002",  # 上证A指
    "000003",  # 上证B指
    "000016",  # 上证50
    "000300",  # 沪深300
    "000905",  # 中证500
    "000852",  # 中证1000
    "000903",  # 中证流通
    "000688",  # 科创50
    "000819",  # 有色金属
    "000012",  # 国债指数
    "000013",  # 上证企债
}

# 判断规则：对于6位代码，000xxx 段同时存在指数（SH）和股票（SZ）
# 无法仅凭代码区分，需要调用方传入 is_index 参数或上下文判断
# 启发式规则：如果代码在 SHINDEX_CODES_6D 集合中，归为 SH；否则按股票规则归为 SZ


# ========== 基础数据类型 ==========

@dataclass
class QuoteData:
    """实时行情数据"""
    symbol: str              # 代码 (如 SH600519)
    name: str                # 名称
    current: float           # 当前价
    open: float              # 开盘价
    high: float              # 最高价
    low: float               # 最低价
    close: float             # 昨收价
    volume: int              # 成交量 (股)
    amount: float            # 成交额 (元)
    percent: float           # 涨跌幅%
    timestamp: str           # 时间戳
    source: str              # 数据来源
    currency: str = 'CNY'    # 货币
    
    # 扩展字段 (可选)
    bid1: Optional[float] = None    # 买一价
    ask1: Optional[float] = None    # 卖一价
    bid_vol1: Optional[int] = None  # 买一量
    ask_vol1: Optional[int] = None  # 卖一量

    # 扩展估值/市值字段 (来自腾讯行情快照)
    pe_ttm: Optional[float] = None              # PE(TTM)
    pb: Optional[float] = None                  # 市净率
    turnover_rate: Optional[float] = None       # 换手率%
    total_market_cap: Optional[float] = None    # 总市值(亿)
    circulating_market_cap: Optional[float] = None  # 流通市值(亿)
    volume_ratio: Optional[float] = None        # 量比
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DepthData:
    """盘口数据 (五档)"""
    symbol: str
    timestamp: str
    source: str

    # 方式1: 使用独立字段（兼容旧代码）
    # 五档买盘
    bid1: float = 0
    bid_vol1: int = 0
    bid2: float = 0
    bid_vol2: int = 0
    bid3: float = 0
    bid_vol3: int = 0
    bid4: float = 0
    bid_vol4: int = 0
    bid5: float = 0
    bid_vol5: int = 0

    # 五档卖盘
    ask1: float = 0
    ask_vol1: int = 0
    ask2: float = 0
    ask_vol2: int = 0
    ask3: float = 0
    ask_vol3: int = 0
    ask4: float = 0
    ask_vol4: int = 0
    ask5: float = 0
    ask_vol5: int = 0

    # 方式2: 使用列表（新Provider推荐）
    bids: List[Dict[str, Union[float, int]]] = field(default_factory=list)
    asks: List[Dict[str, Union[float, int]]] = field(default_factory=list)

    # 委比委差
    wei_bi: Optional[float] = None  # 委比
    wei_cha: Optional[int] = None   # 委差

    def __post_init__(self):
        """初始化后，自动同步bids/asks和独立字段"""
        # 如果提供了bids列表，同步到独立字段
        if self.bids:
            for i, bid in enumerate(self.bids[:5], 1):
                setattr(self, f'bid{i}', bid.get('price', 0))
                setattr(self, f'bid_vol{i}', bid.get('volume', 0))
        # 如果提供了asks列表，同步到独立字段
        if self.asks:
            for i, ask in enumerate(self.asks[:5], 1):
                setattr(self, f'ask{i}', ask.get('price', 0))
                setattr(self, f'ask_vol{i}', ask.get('volume', 0))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def get_bids_list(self) -> List[Dict[str, Union[float, int]]]:
        """获取买盘列表格式"""
        if self.bids:
            return self.bids
        return [
            {"price": self.bid1, "volume": self.bid_vol1},
            {"price": self.bid2, "volume": self.bid_vol2},
            {"price": self.bid3, "volume": self.bid_vol3},
            {"price": self.bid4, "volume": self.bid_vol4},
            {"price": self.bid5, "volume": self.bid_vol5},
        ]

    def get_asks_list(self) -> List[Dict[str, Union[float, int]]]:
        """获取卖盘列表格式"""
        if self.asks:
            return self.asks
        return [
            {"price": self.ask1, "volume": self.ask_vol1},
            {"price": self.ask2, "volume": self.ask_vol2},
            {"price": self.ask3, "volume": self.ask_vol3},
            {"price": self.ask4, "volume": self.ask_vol4},
            {"price": self.ask5, "volume": self.ask_vol5},
        ]


@dataclass
class KlineData:
    """K线数据"""
    date: str                # 日期 YYYY-MM-DD
    open: float              # 开盘价
    high: float              # 最高价
    low: float               # 最低价
    close: float             # 收盘价
    volume: int              # 成交量 (股)
    amount: float            # 成交额 (元)
    
    # 复权因子 (可选)
    adjust_factor: Optional[float] = None
    
    # 扩展字段 (可选)
    turnover: Optional[float] = None  # 换手率
    pct_change: Optional[float] = None  # 涨跌幅
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class IntradayData:
    """分时数据"""
    time: str               # 时间 HH:MM
    price: float            # 价格
    volume: int             # 成交量
    amount: float           # 成交额
    avg_price: float        # 均价
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ========== 财务数据 ==========

@dataclass
class IncomeData:
    """利润表"""
    period: str              # 报告期 YYYYMMDD
    revenue: Optional[float] = None          # 营业收入
    operate_profit: Optional[float] = None   # 营业利润
    total_profit: Optional[float] = None     # 利润总额
    net_profit: Optional[float] = None       # 净利润
    net_profit_attr: Optional[float] = None  # 归母净利润
    eps: Optional[float] = None              # 每股收益
    source: str = 'tushare'
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BalanceData:
    """资产负债表"""
    period: str
    total_assets: Optional[float] = None           # 总资产
    total_liab: Optional[float] = None             # 总负债
    total_equity: Optional[float] = None           # 股东权益
    total_equity_attr: Optional[float] = None      # 归母股东权益
    current_assets: Optional[float] = None         # 流动资产
    current_liab: Optional[float] = None           # 流动负债
    source: str = 'tushare'
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CashFlowData:
    """现金流量表"""
    period: str
    n_cashflow_act: Optional[float] = None         # 经营活动现金流
    n_cashflow_inv_act: Optional[float] = None     # 投资活动现金流
    n_cash_flows_fnc_act: Optional[float] = None   # 筹资活动现金流
    free_cashflow: Optional[float] = None          # 自由现金流
    source: str = 'tushare'
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FinancialIndicator:
    """财务指标"""
    symbol: str                              # 股票代码
    period: str                              # 报告期
    roe: Optional[float] = None              # 净资产收益率
    roa: Optional[float] = None              # 总资产收益率
    gross_margin: Optional[float] = None     # 毛利率
    net_margin: Optional[float] = None       # 净利率
    debt_ratio: Optional[float] = None       # 资产负债率
    current_ratio: Optional[float] = None    # 流动比率
    quick_ratio: Optional[float] = None      # 速动比率
    source: str = 'tushare'
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DividendData:
    """分红数据"""
    period: str              # 分红年度
    div_amount: float        # 每股分红 (元)
    div_ratio: float         # 分红比例
    ex_date: str             # 除权除息日
    source: str = 'tushare'
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ========== 估值数据 ==========

@dataclass
class ValuationData:
    """估值数据"""
    symbol: str
    name: str = ''
    
    # 市盈率
    pe_ttm: Optional[float] = None
    pe_lyr: Optional[float] = None
    pe_forecast: Optional[float] = None
    pe_percentile_10y: Optional[float] = None  # 10年分位
    pe_percentile_5y: Optional[float] = None   # 5年分位
    
    # 市净率
    pb: Optional[float] = None
    pb_percentile_10y: Optional[float] = None
    pb_percentile_5y: Optional[float] = None
    
    # 市销率
    ps_ttm: Optional[float] = None
    ps_percentile_10y: Optional[float] = None
    
    # 股息率
    dividend_yield: Optional[float] = None
    dy_percentile_10y: Optional[float] = None
    
    # ROE
    roe: Optional[float] = None
    roe_avg_10y: Optional[float] = None
    
    # 市值
    market_cap: Optional[float] = None  # 总市值 (亿)
    
    source: str = 'lixinger'
    update_time: str = ''
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ========== 市场数据 ==========

@dataclass
class MoneyFlowData:
    """资金流向数据"""
    date: str
    net_inflow: float        # 净流入 (元)
    main_inflow: float       # 主力流入
    main_outflow: float      # 主力流出
    retail_inflow: float     # 散户流入
    retail_outflow: float    # 散户流出
    source: str = 'tushare'
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LimitUpData:
    """涨停板数据"""
    symbol: str
    name: str
    close: float             # 收盘价
    pct_change: float        # 涨跌幅
    up_stat: str             # 涨停统计 (如 2/3)
    limit_times: int         # 涨停次数
    first_time: str          # 首次涨停时间
    last_time: str           # 最后涨停时间
    reason: str = ''         # 涨停原因
    source: str = 'tushare'
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class IndexComponent:
    """指数成分股"""
    symbol: str
    name: str
    weight: float            # 权重
    source: str = 'tushare'
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TickData:
    """逐笔成交数据"""
    time: str              # 成交时间 HH:MM:SS
    price: float           # 成交价格
    volume: int            # 成交量(股)
    amount: float          # 成交额
    direction: str = ''    # 买卖方向 (买盘/卖盘/中性)
    order_no: Optional[int] = None  # 成交编号

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FinanceSnapshotData:
    """财务快照数据 (mootdx finance)"""
    symbol: str
    circulating_share: Optional[float] = None   # 流通股本(万股)
    total_share: Optional[float] = None         # 总股本(万股)
    total_assets: Optional[float] = None        # 总资产(万元)
    net_assets: Optional[float] = None          # 净资产(万元)
    main_revenue: Optional[float] = None        # 主营收入(万元)
    net_profit: Optional[float] = None          # 净利润(万元)
    eps: Optional[float] = None                 # 每股收益
    bvps: Optional[float] = None               # 每股净资产
    shareholder_count: Optional[int] = None     # 股东人数
    list_date: Optional[str] = None             # 上市日期
    industry: Optional[str] = None              # 行业代码
    source: str = 'tdx'

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class XdxrData:
    """除权除息数据"""
    symbol: str
    date: str                # 除权除息日
    category: str            # 类型 (除权/除息/除权除息)
    bonus_share: float = 0   # 每10股送股
    conver_share: float = 0  # 每10股转增
    cash_div: float = 0      # 每10股派息
    allot_share: float = 0   # 每10股配股
    allot_price: float = 0   # 配股价
    source: str = 'tdx'

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ========== 资讯数据 ==========

@dataclass
class NewsData:
    """新闻数据"""
    title: str
    content: str
    source_name: str         # 来源媒体
    pub_time: str            # 发布时间
    url: str = ''
    symbols: List[str] = field(default_factory=list)  # 相关股票
    source: str = 'tushare'
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AnnouncementData:
    """公告数据"""
    title: str
    ann_type: str            # 公告类型
    pub_time: str
    url: str
    symbol: str
    source: str = 'tushare'
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchReportData:
    """研报数据"""
    title: str
    institution: str         # 机构名称
    analyst: str             # 分析师
    rating: str              # 评级
    pub_time: str
    url: str
    symbol: str
    source: str = 'tushare'
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ========== Provider状态 ==========

@dataclass
class ProviderStatus:
    """Provider健康状态"""
    name: str
    available: bool
    last_success: Optional[str] = None
    last_failure: Optional[str] = None
    failure_count: int = 0
    avg_latency_ms: float = 0
    rate_limit_remaining: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ========== 工具函数 ==========

def parse_symbol_input(raw: str) -> str:
    """
    从自然语言或「名称（代码）」类输入中提取证券代码，便于路由与查询。

    例：「腾讯控股（00700）」「foo (HK00700)」→ 00700 / HK00700；
    已是标准代码时原样返回。
    """
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s:
        return s
    m = re.search(r"[（(]\s*([A-Za-z0-9._]+)\s*[）)]", s)
    if m:
        return m.group(1).strip()
    return s


def detect_market(symbol: str) -> str:
    """
    检测股票市场类型
    返回: a_share, hk, us
    """
    symbol = symbol.upper().strip()
    
    # A股
    if symbol.startswith(('SH', 'SZ', 'BJ')):
        return 'a_share'
    if symbol.endswith(('.SH', '.SZ', '.BJ')):
        return 'a_share'

    # 港股：港交所常见 5 位数字、首位为 0（与理杏仁 _get_exchange 一致），须在 6 位 A 股数字规则之前判断
    if len(symbol) == 5 and symbol.isdigit() and symbol.startswith('0'):
        return 'hk'

    if len(symbol) == 6 and symbol.isdigit():
        if symbol.startswith(('6', '5', '9')):
            return 'a_share'
        else:
            return 'a_share'  # 默认A股
    
    # 港股
    if symbol.startswith('HK') or symbol.endswith('.HK'):
        return 'hk'
    
    # 美股 (默认)
    return 'us'


def a_share_exchange_for_numeric_code(code6: str, is_index: bool = False) -> str:
    """
    六位数字证券代码 → Tushare 所用交易所后缀 SH / SZ / BJ。
    用于纠正「159xxx 误写为 .SH」等后缀与品种不匹配问题（如深市 ETF 159316 应为 .SZ）。

    Args:
        code6: 六位纯数字证券代码
        is_index: 是否为指数代码（显式指定）。若为 True，000xxx → SH，399xxx → SZ。
                  若为 False（默认），使用自动判断：已知指数代码（000300等）自动识别。
    """
    if len(code6) != 6 or not code6.isdigit():
        return 'SH'

    # 已知上交所指数代码（无股票冲突的）
    # 注意：000001/000002/000003 与常见股票冲突，不放入自动检测集合
    SH_INDEX_CODES = {'000300', '000016', '000905', '000852', '000688', '000903', '000819', '000012', '000013'}
    # 已知深交所指数代码
    SZ_INDEX_CODES = {'399001', '399006', '399673', '399102'}

    # 显式指定为指数
    if is_index:
        if code6.startswith('399'):
            return 'SZ'
        return 'SH'

    # 自动检测：已知指数代码
    if code6 in SH_INDEX_CODES:
        return 'SH'
    if code6 in SZ_INDEX_CODES:
        return 'SZ'

    # 北交所常见段（与沪深区分）
    if code6.startswith(('43', '83', '87', '88', '92')):
        return 'BJ'
    # 深市 ETF（如 159xxx）及常见主板/创业板段
    if code6.startswith('159'):
        return 'SZ'
    if code6.startswith(('000', '001', '002', '003', '300', '301')):
        return 'SZ'
    # 沪市主板 / 科创板
    if code6.startswith(('600', '601', '603', '605', '688', '689')):
        return 'SH'
    # 沪市常见 ETF 段
    if code6.startswith(('510', '511', '512', '513', '515', '518', '560', '561', '562', '563', '588')):
        return 'SH'
    # 与历史启发式一致：6/5/9 字头多为沪市（159 已单独归为深市）
    if code6[0] in ('6', '5', '9'):
        return 'SH'
    return 'SZ'


def normalize_symbol(symbol: str, target_format: str = 'standard') -> str:
    """
    标准化股票代码
    
    Args:
        symbol: 原始代码
        target_format: 目标格式
            - 'standard': SH600519 (默认)
            - 'tushare': 600519.SH
            - 'xueqiu': sh600519
            - 'yahoo': 600519.SS
            - 'tdx': 600519 (纯数字)
    
    Returns:
        标准化后的代码
    """
    symbol = symbol.upper().strip()
    market = detect_market(symbol)
    
    # 港股转换 (必须在A股之前，避免00700.HK被误判为A股)
    if market == 'hk':
        # 港股代码提取：00700.HK -> 00700, HK00700 -> 00700
        code = symbol.replace('HK', '').replace('.HK', '').strip()
        # 移除可能残留的.
        code = code.replace('.', '').strip()
        if target_format == 'standard':
            return f"HK{code}"
        elif target_format == 'yahoo':
            return f"{code}.HK"
        elif target_format == 'xueqiu':
            return f"hk{code}"
        return code
    
    # 提取纯代码 (仅A股和美股)
    code = symbol
    if symbol.startswith(('SH', 'SZ', 'BJ')):
        code = symbol[2:]
    elif '.' in symbol:
        code = symbol.split('.')[0]
    
    # A股转换
    if market == 'a_share':
        if target_format == 'standard':
            if symbol.startswith(('SH', 'SZ', 'BJ')):
                return symbol
            elif '.' in symbol:
                parts = symbol.split('.')
                if len(parts) == 2 and len(parts[0]) == 6 and parts[0].isdigit() and parts[1] in (
                    'SH',
                    'SZ',
                    'BJ',
                ):
                    ex = a_share_exchange_for_numeric_code(parts[0])
                    if ex == 'BJ':
                        return f"BJ{parts[0]}"
                    return f"{ex}{parts[0]}"
                parts = symbol.split('.')
                return f"{parts[1]}{parts[0]}"
            elif len(code) == 6:
                ex = a_share_exchange_for_numeric_code(code)
                if ex == 'BJ':
                    return f"BJ{code}"
                return f"{ex}{code}"
        
        elif target_format == 'tushare':
            if '.' in symbol:
                parts = symbol.split('.')
                if len(parts) == 2 and len(parts[0]) == 6 and parts[0].isdigit() and parts[1] in (
                    'SH',
                    'SZ',
                    'BJ',
                ):
                    ex = a_share_exchange_for_numeric_code(parts[0])
                    return f"{parts[0]}.{ex}"
                return symbol
            elif symbol.startswith(('SH', 'SZ', 'BJ')):
                return f"{code}.{symbol[:2]}"
            elif len(code) == 6:
                ex = a_share_exchange_for_numeric_code(code)
                return f"{code}.{ex}"
        
        elif target_format == 'xueqiu':
            if symbol.startswith(('SH', 'SZ', 'BJ')):
                return f"{symbol[:2].lower()}{code}"
            elif '.' in symbol:
                parts = symbol.split('.')
                if len(parts) == 2 and len(parts[0]) == 6 and parts[0].isdigit() and parts[1] in (
                    'SH',
                    'SZ',
                    'BJ',
                ):
                    ex = a_share_exchange_for_numeric_code(parts[0])
                    return f"{ex.lower()}{parts[0]}"
                return f"{parts[1].lower()}{parts[0]}"
            elif len(code) == 6:
                ex = a_share_exchange_for_numeric_code(code)
                return f"{ex.lower()}{code}"
        
        elif target_format == 'yahoo':
            if symbol.startswith('SH'):
                return f"{code}.SS"
            elif symbol.startswith('SZ'):
                return f"{code}.SZ"
            elif symbol.startswith('BJ'):
                return f"{code}.BJ"
            elif '.' in symbol:
                parts = symbol.split('.')
                if len(parts) == 2 and len(parts[0]) == 6 and parts[0].isdigit() and parts[1] in (
                    'SH',
                    'SZ',
                    'BJ',
                ):
                    ex = a_share_exchange_for_numeric_code(parts[0])
                    if ex == 'SH':
                        return f"{parts[0]}.SS"
                    if ex == 'SZ':
                        return f"{parts[0]}.SZ"
                    return f"{parts[0]}.BJ"
                parts = symbol.split('.')
                if parts[1] == 'SH':
                    return f"{parts[0]}.SS"
                return symbol
            elif len(code) == 6:
                ex = a_share_exchange_for_numeric_code(code)
                if ex == 'SH':
                    return f"{code}.SS"
                if ex == 'SZ':
                    return f"{code}.SZ"
                return f"{code}.BJ"
        
        elif target_format == 'tdx':
            return code
    
    # 美股
    return symbol


if __name__ == '__main__':
    # 测试
    print("Testing models...")
    
    # 测试QuoteData
    quote = QuoteData(
        symbol='SH600519',
        name='贵州茅台',
        current=1800.0,
        open=1790.0,
        high=1810.0,
        low=1785.0,
        close=1780.0,
        volume=1000000,
        amount=1800000000,
        percent=1.12,
        timestamp='2026-04-15 15:00:00',
        source='tdx'
    )
    print(f"✓ QuoteData: {quote.name} @ {quote.current}")
    
    # 测试市场检测
    print(f"\n✓ detect_market('SH600519'): {detect_market('SH600519')}")
    print(f"✓ detect_market('600519.SH'): {detect_market('600519.SH')}")
    print(f"✓ detect_market('00700.HK'): {detect_market('00700.HK')}")
    print(f"✓ detect_market('00700'): {detect_market('00700')}")
    print(f"✓ parse_symbol_input('腾讯控股（00700）'): {parse_symbol_input('腾讯控股（00700）')}")
    print(f"✓ detect_market('AAPL'): {detect_market('AAPL')}")
    
    # 测试代码转换
    print(f"\n✓ normalize_symbol('SH600519', 'tushare'): {normalize_symbol('SH600519', 'tushare')}")
    print(f"✓ normalize_symbol('SH600519', 'xueqiu'): {normalize_symbol('SH600519', 'xueqiu')}")
    print(f"✓ normalize_symbol('600519.SH', 'standard'): {normalize_symbol('600519.SH', 'standard')}")
    print(f"✓ normalize_symbol('SH600519', 'yahoo'): {normalize_symbol('SH600519', 'yahoo')}")
    
    print("\n✓ Models test passed!")
