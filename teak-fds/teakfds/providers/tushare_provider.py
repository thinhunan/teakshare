#!/usr/bin/env python3
"""
Tushare Provider - 封装 Tushare Pro 全部功能（HTTP 直连 api.tushare.pro，不依赖 tushare 包）
P1级别 - 历史数据、财务数据主源
"""

from __future__ import annotations

from teakfds.datasource_log import log_info, log_warn, log_error
import sys
import time
from pathlib import Path
from typing import Optional, List, Dict, Union, Any
from datetime import datetime, timedelta
import os

sys.path.insert(0, str(Path(__file__).parent.parent))

from teakfds.datasource_log import log_external_request

from teakfds.models import (
    IncomeData,
    BalanceData,
    CashFlowData,
    KlineData,
    a_share_exchange_for_numeric_code,
    normalize_symbol,
)
from teakfds.providers.base_provider import BaseProvider, ProviderCapabilities
from teakfds.tushare_lite import create_pro_api
from teakfds.providers.tushare_pro_bar_local import pro_bar as tushare_pro_bar
from teakfds.tushare_table import head_records, is_null, records_empty

TUSHARE_HTTP_URL = "https://api.tushare.pro"


class _TushareProProxy:
    """包装 HTTP DataApi（等价 ts.pro_api），记录每次对外 API 调用。"""

    def __init__(self, pro: Any):
        object.__setattr__(self, "_pro", pro)

    def __getattr__(self, name: str):
        raw = getattr(self._pro, name)
        if not callable(raw):
            return raw

        def wrapped(*args: Any, **kwargs: Any):
            sym = kwargs.get("ts_code") or kwargs.get("symbol")
            if sym is None and args:
                sym = args[0]
            t0 = time.perf_counter()
            log_params: Dict[str, Any] = {"pro_attr": name}
            if args:
                log_params["positional_args"] = list(args)
            log_params.update(kwargs)
            try:
                out = raw(*args, **kwargs)
                log_external_request(
                    provider="tushare",
                    method="POST",
                    url=TUSHARE_HTTP_URL,
                    action=name,
                    symbol=str(sym) if sym is not None else None,
                    success=True,
                    status_code=200,
                    duration_ms=(time.perf_counter() - t0) * 1000,
                    message="ok",
                    params=log_params,
                    caller="TushareProvider.pro",
                )
                return out
            except Exception as e:
                log_external_request(
                    provider="tushare",
                    method="POST",
                    url=TUSHARE_HTTP_URL,
                    action=name,
                    symbol=str(sym) if sym is not None else None,
                    success=False,
                    duration_ms=(time.perf_counter() - t0) * 1000,
                    message=str(e)[:1200],
                    params=log_params,
                    caller="TushareProvider.pro",
                )
                raise

        return wrapped

# 积分>5200 或需单独申请权限的接口，禁止经 pro_call 调用，避免无效报错干扰
TUSHARE_PRO_CALL_BLOCKLIST = frozenset({
    'stk_mins', 'rt_k', 'rt_min', 'rt_hk_k', 'rt_etf_k', 'rt_idx_k',
    'etf_basic', 'etf_index', 'etf_share_size',
    'hk_daily',
    'us_income', 'us_balancesheet', 'us_cashflow', 'us_fina_indicator',
    'hk_income', 'hk_balancesheet', 'hk_cashflow', 'hk_fina_indicator',
    'stk_auction', 'major_news', 'news', 'cctv_news', 'npr',
    'dc_hot', 'ccass_hold_detail', 'report_rc',
    'irm_qa_sz', 'irm_qa_sh', 'limit_step', 'limit_cpt_list', 'limit_list_ths',
    'cb_price_chg', 'rt_fut_min',
})


class TushareProvider(BaseProvider):
    """
    Tushare数据提供商
    封装Tushare所有API，保持功能完整性
    """

    name = "tushare"
    display_name = "Tushare"
    priority = 70  # P1级别

    capabilities = ProviderCapabilities(
        supports_kline=True,
        supports_financial=True,
        supports_intraday=False,
        markets=['a_share'],
        kline_periods=['day', 'week', 'month']
    )

    # Token文件路径
    TOKEN_PATHS = [
        Path.home() / 'agents_documents' / 'TUSHARE_TOKEN.txt',
        Path.home() / '.openclaw' / 'credentials' / 'TUSHARE_TOKEN.txt',
    ]

    def __init__(self):
        self.pro = None
        token = self._load_token()
        if token:
            try:
                api = create_pro_api(token)
                if api is not None:
                    self.pro = _TushareProProxy(api)
            except Exception as e:
                log_error(f"Tushare初始化失败: {e}")
        self._cache = {}

    def _load_token(self) -> Optional[str]:
        """加载Tushare Token（优先环境变量，其次文件）"""
        # 1. 检查环境变量
        token = os.environ.get('TUSHARE_TOKEN')
        if token:
            return token.strip()

        # 2. 检查文件
        for path in self.TOKEN_PATHS:
            if path.exists():
                try:
                    return path.read_text().strip()
                except Exception as e:
                    print(f"读取TUSHARE_TOKEN文件失败 {path}: {e}")
                    continue

        return None

    def is_available(self) -> bool:
        """检查是否可用"""
        return self.pro is not None

    def get_status(self):
        """获取Provider状态"""
        from teakfds.models import ProviderStatus
        available = self.is_available()
        return ProviderStatus(
            name=self.name,
            available=available,
            last_success=datetime.now().isoformat() if available else None,
        )

    # ========== 股票基础数据 ==========

    def get_stock_basic(self, ts_code: str = None, name: str = None) -> Optional[Any]:
        """获取股票基础信息"""
        if not self.pro:
            return None
        try:
            return self.pro.stock_basic(ts_code=ts_code, name=name)
        except Exception as e:
            print(f"TushareProvider.get_stock_basic error: {e}")
            return None

    # ========== 行情数据 ==========

    def get_daily(self, ts_code: str, start_date: str = None, end_date: str = None) -> Optional[Any]:
        """获取日线行情"""
        if not self.pro:
            return None
        try:
            if not end_date:
                end_date = datetime.now().strftime('%Y%m%d')
            if not start_date:
                start_date = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')
            return self.pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        except Exception as e:
            print(f"TushareProvider.get_daily error: {e}")
            return None

    # ========== 行情数据扩展 ==========

    def get_weekly(self, ts_code: str, start_date: str = None, end_date: str = None) -> Optional[Any]:
        """获取周线行情"""
        if not self.pro:
            return None
        try:
            if not end_date:
                end_date = datetime.now().strftime('%Y%m%d')
            if not start_date:
                start_date = (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')
            return self.pro.weekly(ts_code=ts_code, start_date=start_date, end_date=end_date)
        except Exception as e:
            print(f"TushareProvider.get_weekly error: {e}")
            return None

    def get_monthly(self, ts_code: str, start_date: str = None, end_date: str = None) -> Optional[Any]:
        """获取月线行情"""
        if not self.pro:
            return None
        try:
            if not end_date:
                end_date = datetime.now().strftime('%Y%m%d')
            if not start_date:
                start_date = (datetime.now() - timedelta(days=1095)).strftime('%Y%m%d')
            return self.pro.monthly(ts_code=ts_code, start_date=start_date, end_date=end_date)
        except Exception as e:
            print(f"TushareProvider.get_monthly error: {e}")
            return None

    def get_stock_list(self, market: str = 'SSE') -> Optional[Any]:
        """获取股票列表"""
        if not self.pro:
            return None
        try:
            return self.pro.stock_basic(exchange=market, list_status='L')
        except Exception as e:
            print(f"TushareProvider.get_stock_list error: {e}")
            return None

    # ========== K线统一接口 ==========

    def kline(self,
              symbol: str,
              period: str = 'day',
              count: int = 30,
              start_date: str = None,
              end_date: str = None) -> Optional[List[KlineData]]:
        """
        获取K线数据 - 统一接口

        Args:
            symbol: 股票代码 (如 SH600519)
            period: 周期 ('1min', '5min', '15min', '30min', '60min', 'day', 'week', 'month')
            count: 获取条数
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)

        Returns:
            KlineData 列表或None
        """
        if not self.pro:
            return None

        ts_code = self.normalize_code(symbol)

        try:
            # 根据period选择对应的API
            if period == 'day':
                df = self.get_daily(ts_code, start_date, end_date)
            elif period == 'week':
                df = self.get_weekly(ts_code, start_date, end_date)
            elif period == 'month':
                df = self.get_monthly(ts_code, start_date, end_date)
            elif period in ['1min', '5min', '15min', '30min', '60min']:
                # stk_mins 需单独权限，5200 积分默认不可用；分钟线请用 FDS.kline(period=...) 走腾讯/通达信等
                print("TushareProvider.kline: 分钟线已禁用（请使用 FinanceDataSource.kline 的公开源路由）")
                return None
            else:
                print(f"TushareProvider.kline: 不支持的周期 {period}")
                return None

            rows = df
            if records_empty(rows):
                return None

            # 转换为KlineData列表
            results = []
            for row in rows:
                try:
                    if not isinstance(row, dict):
                        row = dict(row)
                    # 处理日期格式
                    trade_date = str(row.get('trade_date', ''))
                    if len(trade_date) == 8:
                        date_str = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
                    else:
                        date_str = trade_date

                    kline = KlineData(
                        date=date_str,
                        open=float(row.get('open', 0)) if not is_null(row.get('open')) else 0,
                        high=float(row.get('high', 0)) if not is_null(row.get('high')) else 0,
                        low=float(row.get('low', 0)) if not is_null(row.get('low')) else 0,
                        close=float(row.get('close', 0)) if not is_null(row.get('close')) else 0,
                        volume=int(row.get('vol', 0)) if not is_null(row.get('vol')) else 0,
                        amount=float(row.get('amount', 0)) if not is_null(row.get('amount')) else 0,
                        pct_change=float(row.get('pct_chg', 0)) if not is_null(row.get('pct_chg')) else None
                    )
                    results.append(kline)
                except Exception as e:
                    print(f"TushareProvider.kline row error: {e}")
                    continue

            # 限制返回条数
            if count and len(results) > count:
                results = results[:count]

            return results

        except Exception as e:
            print(f"TushareProvider.kline error: {e}")
            return None

    # ========== 财务数据 ==========

    def get_income(self, ts_code: str, period: str = None) -> Optional[Any]:
        """获取利润表 (list[dict]，与 Tushare 列名一致)"""
        if not self.pro:
            return None
        try:
            if period:
                return self.pro.income(ts_code=ts_code, period=period)
            else:
                rows = self.pro.income(ts_code=ts_code)
                if not records_empty(rows):
                    return head_records(rows, 1)
                return rows
        except Exception as e:
            print(f"TushareProvider.get_income error: {e}")
            return None

    def get_financial_indicator(self, ts_code: str, period: str = None) -> Optional[Any]:
        """获取财务指标"""
        if not self.pro:
            return None
        try:
            if period:
                return self.pro.fina_indicator(ts_code=ts_code, period=period)
            else:
                # 不指定period，获取最新数据
                rows = self.pro.fina_indicator(ts_code=ts_code)
                if not records_empty(rows):
                    return head_records(rows, 1)
                return rows
        except Exception as e:
            print(f"TushareProvider.get_financial_indicator error: {e}")
            return None

    # ========== 估值数据 ==========

    def get_daily_basic(self, ts_code: str = None, trade_date: str = None) -> Optional[Any]:
        """获取每日指标(PE/PB等)"""
        if not self.pro:
            return None
        try:
            if not trade_date:
                trade_date = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
            return self.pro.daily_basic(ts_code=ts_code, trade_date=trade_date)
        except Exception as e:
            print(f"TushareProvider.get_daily_basic error: {e}")
            return None

    def get_money_flow(self, ts_code: str, start_date: str = None, end_date: str = None) -> Optional[Any]:
        """获取资金流向"""
        if not self.pro:
            return None
        try:
            if not end_date:
                end_date = datetime.now().strftime('%Y%m%d')
            if not start_date:
                start_date = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')
            return self.pro.moneyflow(ts_code=ts_code, start_date=start_date, end_date=end_date)
        except Exception as e:
            print(f"TushareProvider.get_money_flow error: {e}")
            return None

    def get_balancesheet(self, ts_code: str, period: str = None) -> Optional[Any]:
        """获取资产负债表 (list[dict])"""
        if not self.pro:
            return None
        try:
            if period:
                return self.pro.balancesheet(ts_code=ts_code, period=period)
            else:
                rows = self.pro.balancesheet(ts_code=ts_code)
                if not records_empty(rows):
                    return head_records(rows, 4)
                return rows
        except Exception as e:
            print(f"TushareProvider.get_balancesheet error: {e}")
            return None

    def get_cashflow(self, ts_code: str, period: str = None) -> Optional[Any]:
        """获取现金流量表 (list[dict])"""
        if not self.pro:
            return None
        try:
            if period:
                return self.pro.cashflow(ts_code=ts_code, period=period)
            else:
                rows = self.pro.cashflow(ts_code=ts_code)
                if not records_empty(rows):
                    return head_records(rows, 4)
                return rows
        except Exception as e:
            print(f"TushareProvider.get_cashflow error: {e}")
            return None

    def get_pro_bar(self, ts_code: str, start_date: str = None, end_date: str = None,
                    adj: str = 'qfq', freq: str = 'D') -> Optional[Any]:
        """获取复权行情

        Args:
            ts_code: 股票代码
            start_date: 开始日期 YYYYMMDD
            end_date: 结束日期 YYYYMMDD
            adj: 复权类型 qfq(前复权)/hfq(后复权)/None(不复权)
            freq: 频率 D(日线)/W(周线)/M(月线)
        """
        if not self.pro:
            return None
        t0 = time.perf_counter()
        try:
            out = tushare_pro_bar(
                ts_code=ts_code,
                pro_api=self.pro,
                start_date=start_date,
                end_date=end_date,
                adj=adj,
                freq=freq,
            )
            log_external_request(
                provider="tushare",
                method="POST",
                url=TUSHARE_HTTP_URL,
                action="pro_bar",
                symbol=ts_code,
                success=True,
                status_code=200,
                duration_ms=(time.perf_counter() - t0) * 1000,
                message="ok",
                params={
                    "ts_code": ts_code,
                    "start_date": start_date,
                    "end_date": end_date,
                    "adj": adj,
                    "freq": freq,
                },
                caller="TushareProvider.get_pro_bar",
            )
            return out
        except Exception as e:
            log_external_request(
                provider="tushare",
                method="POST",
                url=TUSHARE_HTTP_URL,
                action="pro_bar",
                symbol=ts_code,
                success=False,
                duration_ms=(time.perf_counter() - t0) * 1000,
                message=str(e)[:1200],
                params={
                    "ts_code": ts_code,
                    "start_date": start_date,
                    "end_date": end_date,
                    "adj": adj,
                    "freq": freq,
                },
                caller="TushareProvider.get_pro_bar",
            )
            print(f"TushareProvider.get_pro_bar error: {e}")
            return None

    def get_index_basic(self, market: str = None) -> Optional[Any]:
        """获取指数基础信息"""
        if not self.pro:
            return None
        try:
            if market:
                return self.pro.index_basic(market=market)
            return self.pro.index_basic()
        except Exception as e:
            print(f"TushareProvider.get_index_basic error: {e}")
            return None

    def get_index_daily(self, ts_code: str, start_date: str = None,
                        end_date: str = None) -> Optional[Any]:
        """获取指数日线行情"""
        if not self.pro:
            return None
        try:
            if not end_date:
                end_date = datetime.now().strftime('%Y%m%d')
            if not start_date:
                start_date = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')
            return self.pro.index_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        except Exception as e:
            print(f"TushareProvider.get_index_daily error: {e}")
            return None

    def get_moneyflow_hsgt(self, start_date: str = None, end_date: str = None) -> Optional[Any]:
        """获取沪深港通资金流向（北向资金）"""
        if not self.pro:
            return None
        try:
            if not end_date:
                end_date = datetime.now().strftime('%Y%m%d')
            if not start_date:
                start_date = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')
            return self.pro.moneyflow_hsgt(start_date=start_date, end_date=end_date)
        except Exception as e:
            print(f"TushareProvider.get_moneyflow_hsgt error: {e}")
            return None

    def get_hsgt_top10(self, trade_date: str = None) -> Optional[Any]:
        """获取沪深港通十大成交股"""
        if not self.pro:
            return None
        try:
            if not trade_date:
                trade_date = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
            return self.pro.hsgt_top10(trade_date=trade_date)
        except Exception as e:
            print(f"TushareProvider.get_hsgt_top10 error: {e}")
            return None

    def get_top_list(self, trade_date: str = None) -> Optional[Any]:
        """获取龙虎榜每日明细"""
        if not self.pro:
            return None
        try:
            if not trade_date:
                trade_date = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
            return self.pro.top_list(trade_date=trade_date)
        except Exception as e:
            print(f"TushareProvider.get_top_list error: {e}")
            return None

    def get_limit_list(self, trade_date: str = None) -> Optional[Any]:
        """获取每日涨跌停股票"""
        if not self.pro:
            return None
        try:
            if not trade_date:
                trade_date = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
            return self.pro.limit_list(trade_date=trade_date)
        except Exception as e:
            print(f"TushareProvider.get_limit_list error: {e}")
            return None

    # ========== 分钟线数据 ==========

    def get_stk_mins(self, ts_code: str, start_date: str = None, end_date: str = None,
                     freq: str = '1min') -> Optional[Any]:
        """已禁用：stk_mins 需单独开通权限，与 5200 积分档常见权限不符。请使用 FDS.stk_mins。"""
        print("TushareProvider.get_stk_mins: 已禁用，请使用 FinanceDataSource.stk_mins（非 Tushare 源）")
        return None

    def get_adj_factor_map(self, symbol: str, start_date: str, end_date: str) -> Dict[str, float]:
        """按交易日返回复权因子 {trade_date(YYYYMMDD): adj_factor}，用于与通达信未复权日线组合。"""
        if not self.pro:
            return {}
        ts_code = self.normalize_code(symbol)
        s = str(start_date).replace('-', '')[:8]
        e = str(end_date).replace('-', '')[:8]
        if s > e:
            s, e = e, s
        try:
            adj_rows = self.pro.adj_factor(ts_code=ts_code, start_date=s, end_date=e)
            if records_empty(adj_rows):
                return {}
            factors: Dict[str, float] = {}
            for row in adj_rows:
                if not isinstance(row, dict):
                    row = dict(row)
                factors[str(row["trade_date"])] = float(row["adj_factor"])
            return factors
        except Exception as ex:
            print(f"TushareProvider.get_adj_factor_map error: {ex}")
            return {}

    # ========== 业绩预告 ==========

    def get_forecast(self, ts_code: str, start_date: str = None, end_date: str = None) -> Optional[Any]:
        """获取业绩预告

        Args:
            ts_code: 股票代码
            start_date: 公告开始日期 YYYYMMDD
            end_date: 公告结束日期 YYYYMMDD
        """
        if not self.pro:
            return None
        try:
            if not end_date:
                end_date = datetime.now().strftime('%Y%m%d')
            if not start_date:
                start_date = (datetime.now() - timedelta(days=90)).strftime('%Y%m%d')
            return self.pro.forecast(ts_code=ts_code, start_date=start_date, end_date=end_date)
        except Exception as e:
            print(f"TushareProvider.get_forecast error: {e}")
            return None

    # ========== 业绩快报 ==========

    def get_express(self, ts_code: str, start_date: str = None, end_date: str = None) -> Optional[Any]:
        """获取业绩快报

        Args:
            ts_code: 股票代码
            start_date: 公告开始日期 YYYYMMDD
            end_date: 公告结束日期 YYYYMMDD
        """
        if not self.pro:
            return None
        try:
            if not end_date:
                end_date = datetime.now().strftime('%Y%m%d')
            if not start_date:
                start_date = (datetime.now() - timedelta(days=90)).strftime('%Y%m%d')
            return self.pro.express(ts_code=ts_code, start_date=start_date, end_date=end_date)
        except Exception as e:
            print(f"TushareProvider.get_express error: {e}")
            return None

    # ========== 宏观数据 ==========

    def get_cn_cpi(self, month: str = None) -> Optional[Any]:
        """获取CPI数据（居民消费价格指数）

        Args:
            month: 月份 YYYYMM，默认最近12个月
        """
        if not self.pro:
            return None
        try:
            if month:
                return self.pro.cn_cpi(month=month)
            else:
                rows = self.pro.cn_cpi()
                if not records_empty(rows):
                    return head_records(rows, 12)
                return rows
        except Exception as e:
            print(f"TushareProvider.get_cn_cpi error: {e}")
            return None

    def get_cn_ppi(self, month: str = None) -> Optional[Any]:
        """获取PPI数据（工业生产者出厂价格指数）

        Args:
            month: 月份 YYYYMM，默认最近12个月
        """
        if not self.pro:
            return None
        try:
            if month:
                return self.pro.cn_ppi(month=month)
            else:
                rows = self.pro.cn_ppi()
                if not records_empty(rows):
                    return head_records(rows, 12)
                return rows
        except Exception as e:
            print(f"TushareProvider.get_cn_ppi error: {e}")
            return None

    def get_cn_pmi(self, month: str = None) -> Optional[Any]:
        """获取PMI数据（采购经理指数）

        Args:
            month: 月份 YYYYMM，默认最近12个月
        """
        if not self.pro:
            return None
        try:
            if month:
                return self.pro.cn_pmi(month=month)
            else:
                rows = self.pro.cn_pmi()
                if not records_empty(rows):
                    return head_records(rows, 12)
                return rows
        except Exception as e:
            print(f"TushareProvider.get_cn_pmi error: {e}")
            return None

    def get_cn_gdp(self, quarter: str = None) -> Optional[Any]:
        """获取GDP数据（国内生产总值）

        Args:
            quarter: 季度 YYYYQ，默认最近8个季度
        """
        if not self.pro:
            return None
        try:
            if quarter:
                return self.pro.cn_gdp(q=quarter)
            else:
                rows = self.pro.cn_gdp()
                if not records_empty(rows):
                    return head_records(rows, 8)
                return rows
        except Exception as e:
            print(f"TushareProvider.get_cn_gdp error: {e}")
            return None

    def get_cn_m(self, month: str = None) -> Optional[Any]:
        """获取M2/M1货币供应量数据

        Args:
            month: 月份 YYYYMM，默认最近12个月
        """
        if not self.pro:
            return None
        try:
            if month:
                return self.pro.cn_m(month=month)
            else:
                rows = self.pro.cn_m()
                if not records_empty(rows):
                    return head_records(rows, 12)
                return rows
        except Exception as e:
            print(f"TushareProvider.get_cn_m error: {e}")
            return None

    def get_shibor(self, date: str = None) -> Optional[Any]:
        """获取Shibor利率数据

        Args:
            date: 日期 YYYYMMDD，默认最近10个交易日
        """
        if not self.pro:
            return None
        try:
            if date:
                return self.pro.shibor(date=date)
            else:
                rows = self.pro.shibor()
                if not records_empty(rows):
                    return head_records(rows, 10)
                return rows
        except Exception as e:
            print(f"TushareProvider.get_shibor error: {e}")
            return None

    # ========== 统一接口方法 (FinanceDataSource调用) ==========

    def income(self, symbol: str, period: str = None) -> Optional[IncomeData]:
        """
        获取利润表 - 统一接口

        Args:
            symbol: 股票代码 (如 SH600519)
            period: 报告期 (YYYYMMDD)，None表示最新

        Returns:
            IncomeData 或 None
        """
        from teakfds.adapters.financial_adapter import FinancialAdapter

        if not self.pro:
            return None

        ts_code = self.normalize_code(symbol)
        rows = self.get_income(ts_code, period)

        if records_empty(rows):
            return None

        try:
            # 使用适配器转换为统一模型
            income_list = FinancialAdapter.from_tushare_income(rows, symbol)
            if income_list and len(income_list) > 0:
                return income_list[0]  # 返回最新的一条
            return None
        except Exception as e:
            print(f"TushareProvider.income error: {e}")
            return None

    def balance_sheet(self, symbol: str, period: str = None) -> Optional[BalanceData]:
        """
        获取资产负债表 - 统一接口

        Args:
            symbol: 股票代码 (如 SH600519)
            period: 报告期 (YYYYMMDD)，None表示最新

        Returns:
            BalanceData 或 None
        """
        from teakfds.adapters.financial_adapter import FinancialAdapter

        if not self.pro:
            return None

        ts_code = self.normalize_code(symbol)
        rows = self.get_balancesheet(ts_code, period)

        if records_empty(rows):
            return None

        try:
            # 使用适配器转换为统一模型
            balance_list = FinancialAdapter.from_tushare_balance(rows, symbol)
            if balance_list and len(balance_list) > 0:
                return balance_list[0]  # 返回最新的一条
            return None
        except Exception as e:
            print(f"TushareProvider.balance_sheet error: {e}")
            return None

    def cash_flow(self, symbol: str, period: str = None) -> Optional[CashFlowData]:
        """
        获取现金流量表 - 统一接口

        Args:
            symbol: 股票代码 (如 SH600519)
            period: 报告期 (YYYYMMDD)，None表示最新

        Returns:
            CashFlowData 或 None
        """
        from teakfds.adapters.financial_adapter import FinancialAdapter

        if not self.pro:
            return None

        ts_code = self.normalize_code(symbol)
        rows = self.get_cashflow(ts_code, period)

        if records_empty(rows):
            return None

        try:
            # 使用适配器转换为统一模型
            cashflow_list = FinancialAdapter.from_tushare_cashflow(rows, symbol)
            if cashflow_list and len(cashflow_list) > 0:
                return cashflow_list[0]  # 返回最新的一条
            return None
        except Exception as e:
            print(f"TushareProvider.cash_flow error: {e}")
            return None

    def financial_indicator(self, symbol: str, period: str = None):
        """获取财务指标 - 统一接口"""
        from teakfds.models import FinancialIndicator as ModelsFinancialIndicator

        ts_code = self.normalize_code(symbol)
        rows = self.get_financial_indicator(ts_code, period)

        if records_empty(rows):
            return None

        try:
            row = rows[0]
            return ModelsFinancialIndicator(
                symbol=symbol,
                period=str(row.get('end_date', '')),
                roe=float(row.get('roe', 0)) if not is_null(row.get('roe')) else 0,
                roa=float(row.get('roa', 0)) if not is_null(row.get('roa')) else 0,
                gross_margin=float(row.get('grossprofit_margin', 0)) if not is_null(row.get('grossprofit_margin')) else 0,
                net_margin=float(row.get('netprofit_margin', 0)) if not is_null(row.get('netprofit_margin')) else 0,
                debt_ratio=float(row.get('debt_to_assets', 0)) if not is_null(row.get('debt_to_assets')) else 0,
                current_ratio=float(row.get('current_ratio', 0)) if not is_null(row.get('current_ratio')) else 0,
                quick_ratio=float(row.get('quick_ratio', 0)) if not is_null(row.get('quick_ratio')) else 0,
                source='tushare'
            )
        except Exception as e:
            print(f"TushareProvider.financial_indicator error: {e}")
            return None

    def valuation(self, symbol: str):
        """获取估值数据 - 统一接口"""
        from teakfds.models import ValuationData as ModelsValuationData

        ts_code = self.normalize_code(symbol)
        rows = self.get_daily_basic(ts_code)

        if records_empty(rows):
            return None

        try:
            row = rows[0]
            return ModelsValuationData(
                symbol=symbol,
                name='',
                pe_ttm=float(row.get('pe_ttm', 0)) if not is_null(row.get('pe_ttm')) else None,
                pe_lyr=float(row.get('pe', 0)) if not is_null(row.get('pe')) else None,
                pb=float(row.get('pb', 0)) if not is_null(row.get('pb')) else None,
                ps_ttm=float(row.get('ps', 0)) if not is_null(row.get('ps')) else None,
                dividend_yield=float(row.get('dv_ttm', 0)) if not is_null(row.get('dv_ttm')) else None,
                market_cap=float(row.get('total_mv', 0)) / 10000 if not is_null(row.get('total_mv')) else None,  # 万元->亿元
                source='tushare'
            )
        except Exception as e:
            print(f"TushareProvider.valuation error: {e}")
            return None

    def money_flow(self, symbol: str, days: int = 30):
        """获取资金流向 - 统一接口"""
        ts_code = self.normalize_code(symbol)
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
        return self.get_money_flow(ts_code, start_date, end_date)

    # ========== 逃生舱功能 ==========

    def pro_call(self, api: str, **kwargs) -> Optional[Any]:
        """
        直接调用 Tushare Pro API 的任意方法 - 逃生舱功能

        当封装的方法不能满足需求时，可以直接调用底层 API

        Args:
            api: API 方法名 (如 'daily', 'income', 'balancesheet' 等)
            **kwargs: 传递给 API 的参数

        Returns:
            list[dict] 或 None（每行一条记录，键为字段名）

        Examples:
            # 直接调用 daily API
            rows = provider.pro_call('daily', ts_code='600519.SH', start_date='20240101')

            # 调用新股列表
            rows = provider.pro_call('new_share', start_date='20240101', end_date='20241231')
        """
        if not self.pro:
            print("TushareProvider.pro_call error: Tushare not available")
            return None

        if api in TUSHARE_PRO_CALL_BLOCKLIST:
            print(
                f"TushareProvider.pro_call: '{api}' 已在封禁列表（>5200 积分或需单独申请权限），已跳过"
            )
            return None

        try:
            if hasattr(self.pro, api):
                method = getattr(self.pro, api)
                return method(**kwargs)
            else:
                print(f"TushareProvider.pro_call error: API '{api}' not found")
                return None
        except Exception as e:
            print(f"TushareProvider.pro_call error ({api}): {e}")
            return None

    # ========== 工具方法 ==========

    # ========== F10数据接口 ==========

    def get_insider_trading(self, ts_code: str, **kwargs) -> Optional[List[Dict]]:
        """获取高管增减持数据 (stk_holdertrade)

        Args:
            ts_code: 股票代码，如 300720.SZ
            **kwargs: 其他参数（如 start_date, end_date）

        Returns:
            list[dict]: 高管增减持记录，字段包括 holder_name, holder_type, in_de, change_vol 等
        """
        return self._safe_query('stk_holdertrade', ts_code=ts_code, **kwargs)

    def get_top10_holders(self, ts_code: str, **kwargs) -> Optional[List[Dict]]:
        """获取十大股东数据 (top10_holders)

        Args:
            ts_code: 股票代码，如 300720.SZ
            **kwargs: 其他参数（如 period）

        Returns:
            list[dict]: 十大股东记录，字段包括 ann_date, end_date, holder_name, hold_amount 等
        """
        return self._safe_query('top10_holders', ts_code=ts_code, **kwargs)

    def get_top10_floatholders(self, ts_code: str, **kwargs) -> Optional[List[Dict]]:
        """获取十大流通股东数据 (top10_floatholders)

        Args:
            ts_code: 股票代码，如 300.SZ
            **kwargs: 其他参数（如 period）

        Returns:
            list[dict]: 十大流通股东记录，字段包括 ann_date, end_date, holder_name, hold_amount 等
        """
        return self._safe_query('top10_floatholders', ts_code=ts_code, **kwargs)

    def get_cyq_perf(self, ts_code: str, **kwargs) -> Optional[List[Dict]]:
        """获取股东人数/筹码分布数据 (cyq_perf)

        Args:
            ts_code: 股票代码，如 300720.SZ
            **kwargs: 其他参数（如 start_date, end_date）

        Returns:
            list[dict]: 筹码分布记录，字段包括 his_low, his_high, his_width, cost_5pct 等
        """
        return self._safe_query('cyq_perf', ts_code=ts_code, **kwargs)

    def get_managers(self, ts_code: str, **kwargs) -> Optional[List[Dict]]:
        """获取公司高管数据 (stk_managers)

        Args:
            ts_code: 股票代码，如 300720.SZ
            **kwargs: 其他参数

        Returns:
            list[dict]: 高管信息记录，字段包括 ann_date, name, title, resume 等
        """
        return self._safe_query('stk_managers', ts_code=ts_code, **kwargs)

    def get_fina_mainbz(self, ts_code: str, type: str = 'P', **kwargs) -> Optional[List[Dict]]:
        """获取主营构成数据 (fina_mainbz)

        Args:
            ts_code: 股票代码，如 300720.SZ
            type: 类型 P(按产品)/D(按地区)，默认P
            **kwargs: 其他参数（如 period）

        Returns:
            list[dict]: 主营构成记录，字段包括 end_date, type, item_name, bz_sales 等
        """
        return self._safe_query('fina_mainbz', ts_code=ts_code, type=type, **kwargs)

    def get_share_float(self, ts_code: str, **kwargs) -> Optional[List[Dict]]:
        """获取限售解禁数据 (share_float)

        Args:
            ts_code: 股票代码，如 300720.SZ
            **kwargs: 其他参数（如 ann_date）

        Returns:
            list[dict]: 限售解禁记录，字段包括 ann_date, float_date, float_share, float_ratio 等
        """
        return self._safe_query('share_float', ts_code=ts_code, **kwargs)

    def get_stk_surv(self, ts_code: str, **kwargs) -> Optional[List[Dict]]:
        """获取调研活动数据 (stk_surv)

        Args:
            ts_code: 股票代码，如 300720.SZ
            **kwargs: 其他参数（如 start_date, end_date）

        Returns:
            list[dict]: 调研活动记录，字段包括 surv_date, surv_place, org_name, org_type 等
        """
        return self._safe_query('stk_surv', ts_code=ts_code, **kwargs)

    def _safe_query(self, api: str, **kwargs) -> Optional[List[Dict]]:
        """安全查询Tushare API，返回list[dict]格式"""
        if not self.pro:
            return None
        try:
            result = self.pro_call(api, **kwargs)
            if records_empty(result):
                return None
            # 确保返回list[dict]
            if isinstance(result, list):
                return [dict(row) if not isinstance(row, dict) else row for row in result]
            return None
        except Exception as e:
            log_error(f"TushareProvider._safe_query({api}) error: {e}")
            return None

    @staticmethod
    def normalize_code(code: str) -> str:
        """代码格式标准化 SH600519 -> 600519.SH（含 159xxx 深市 ETF 与 ts_code 带点格式）。"""
        s = (code or "").upper().strip()
        if not s:
            return s
        if "." in s:
            parts = s.split(".")
            if (
                len(parts) == 2
                and len(parts[0]) == 6
                and parts[0].isdigit()
                and parts[1] in ("SH", "SZ", "BJ")
            ):
                ex = a_share_exchange_for_numeric_code(parts[0])
                return f"{parts[0]}.{ex}"
            return s
        if s.startswith(("SH", "SZ", "BJ")):
            mkt = s[:2]
            num = s[2:]
            if len(num) == 6 and num.isdigit():
                return f"{num}.{mkt}"
            return s
        if len(s) == 6 and s.isdigit():
            ex = a_share_exchange_for_numeric_code(s)
            return f"{s}.{ex}"
        return s

    @staticmethod
    def to_market_code(ts_code: str) -> str:
        """Tushare 代码转 FDS 标准码 600519.SH -> SH600519"""
        if not ts_code:
            return ts_code
        return normalize_symbol(ts_code, "standard")


# 全局实例
tushare_provider = TushareProvider()
