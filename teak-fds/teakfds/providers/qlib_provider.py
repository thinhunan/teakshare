#!/usr/bin/env python3
"""
QlibProvider - Qlib数据源Provider（直接集成版）

数据特点:
- A股日线，2000年至今，覆盖 6000+ 只股票
- 前复权数据 (qfq)，自带复权因子
- 数据质量高，经过 qlib 社区校验
- 仅支持 A 股日线（不支持港股、分钟线）

运行环境:
- qlib 已安装在系统 Python 3.14（从源码 pip install -e ~/agents_documents/qlib）
- 数据目录: ~/.qlib/qlib_data/cn_data
- 无需 conda 环境、无需子进程桥接
"""

import os
import math
import logging
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from teakfds.providers.base_provider import HistoricalProvider, ProviderCapabilities, ProviderStatus
from teakfds.models import (
    KlineData,
    normalize_symbol,
    detect_market
)
from teakfds.datasource_log import log_info, log_warn, log_error

# Qlib 日志降噪
logging.getLogger("qlib").setLevel(logging.WARNING)

# Qlib 数据目录
QLIB_DATA_DIR = os.path.expanduser("~/.qlib/qlib_data/cn_data")

# qlib 初始化状态（全局只 init 一次）
_qlib_initialized = False


def _ensure_qlib_init():
    """确保 qlib 已初始化（全局只执行一次）"""
    global _qlib_initialized
    if _qlib_initialized:
        return True

    if not os.path.exists(QLIB_DATA_DIR):
        log_warn(f"QlibProvider: data dir not found: {QLIB_DATA_DIR}")
        return False

    try:
        import qlib
        from qlib.config import REG_CN
        qlib.init(provider_uri=QLIB_DATA_DIR, region=REG_CN)
        _qlib_initialized = True
        log_info("QlibProvider: qlib initialized successfully")
        return True
    except Exception as e:
        log_error(f"QlibProvider: qlib init failed: {e}")
        return False


class QlibProvider(HistoricalProvider):
    """
    Qlib数据源Provider（直接集成版）

    直接 import qlib，无需子进程桥接。

    优势:
    - 数据自带前复权因子，无需额外计算
    - 数据范围广 (2000年至今)
    - 数据质量高 (经过 qlib 社区校验)
    - 直接调用，无 subprocess 开销

    限制:
    - 仅支持A股日线
    - 不支持港股
    """

    name = "qlib"
    display_name = "Qlib量化数据"
    priority = 160  # A股日线最高优先级

    capabilities = ProviderCapabilities(
        supports_kline=True,
        supports_financial=False,
        markets=['a_share'],
        kline_periods=['day']
    )

    def __init__(self):
        super().__init__()
        self._available = None

    def _symbol_to_qlib(self, symbol: str) -> Optional[str]:
        """
        将 FDS 标准代码转换为 Qlib 格式

        FDS: SH600519, SZ000001, 600519.SH, 000001.SZ
        Qlib: SH600519, SZ000001

        仅支持A股，港股返回 None
        """
        market = detect_market(symbol)
        if market != 'a_share':
            return None

        code = normalize_symbol(symbol, 'tdx')  # 纯数字

        if symbol.upper().startswith('SH') or symbol.upper().endswith('.SH'):
            prefix = 'SH'
        elif symbol.upper().startswith('SZ') or symbol.upper().endswith('.SZ'):
            prefix = 'SZ'
        elif symbol.upper().startswith('BJ') or symbol.upper().endswith('.BJ'):
            prefix = 'BJ'
        else:
            if code.startswith(('6', '5', '9')):
                prefix = 'SH'
            elif code.startswith(('0', '1', '2', '3')):
                prefix = 'SZ'
            elif code.startswith(('4', '8')):
                prefix = 'BJ'
            else:
                prefix = 'SH'

        return f"{prefix}{code}"

    def _fetch_kline_df(self, symbol: str, fields: list, start_time: str = None, end_time: str = None):
        """
        从 Qlib 获取 DataFrame

        Args:
            symbol: Qlib 格式代码 (如 SH600519)
            fields: 字段列表 (如 ["$open", "$close", "$volume", "$factor"])
            start_time: 开始日期 "YYYY-MM-DD"
            end_time: 结束日期 "YYYY-MM-DD"

        Returns:
            DataFrame 或 None
        """
        if not _ensure_qlib_init():
            return None

        try:
            from qlib.data import D
            df = D.features([symbol], fields=fields, start_time=start_time, end_time=end_time)
            return df if df is not None and not df.empty else None
        except Exception as e:
            log_error(f"QlibProvider: fetch failed for {symbol}: {e}")
            return None

    @staticmethod
    def _convert_date(date_str: str) -> str:
        """YYYYMMDD -> YYYY-MM-DD"""
        if not date_str:
            return None
        date_str = date_str.replace('-', '')
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

    def is_available(self) -> bool:
        """检查 Qlib 是否可用"""
        if self._available is not None:
            now = datetime.now().timestamp()
            if now - self._last_check_time < self._check_interval:
                return self._available

        # 检查数据目录
        if not os.path.exists(QLIB_DATA_DIR):
            self._available = False
            self._last_check_time = datetime.now().timestamp()
            return False

        # 检查能否 import qlib
        try:
            import qlib
        except ImportError:
            self._available = False
            self._last_check_time = datetime.now().timestamp()
            log_warn("QlibProvider: qlib not installed")
            return False

        # 尝试初始化
        if not _ensure_qlib_init():
            self._available = False
            self._last_check_time = datetime.now().timestamp()
            return False

        # 快速数据校验
        try:
            from qlib.data import D
            dates = D.calendar(freq="day")
            if len(dates) > 0:
                self._available = True
                self._last_check_time = datetime.now().timestamp()
                log_info(f"QlibProvider available: {dates[0]} ~ {dates[-1]}, {len(dates)} trading days")
                return True
        except Exception as e:
            log_warn(f"QlibProvider: calendar check failed: {e}")

        self._available = False
        self._last_check_time = datetime.now().timestamp()
        return False

    def get_status(self) -> ProviderStatus:
        """获取 Provider 状态"""
        return ProviderStatus(
            name=self.name,
            available=self.is_available(),
            last_success=datetime.now().isoformat() if self.is_available() else None
        )

    def _df_to_klines(self, df, adjust: str = 'qfq', count: int = 0) -> List[KlineData]:
        """
        将 Qlib DataFrame 转换为 KlineData 列表

        Args:
            df: Qlib D.features() 返回的 DataFrame
            adjust: 'qfq'前复权, 'hfq'后复权, 'none'不复权
            count: 取最后 N 条，0=全部
        """
        if count and len(df) > count:
            df = df.iloc[-count:]

        results = []
        for (inst, dt), row in df.iterrows():
            date_str = dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt)[:10]

            # 读取原始字段
            factor = row.get("$factor")
            factor_val = float(factor) if factor is not None and not math.isnan(float(factor)) else None

            open_qfq = float(row["$open"])
            high_qfq = float(row["$high"])
            low_qfq = float(row["$low"])
            close_qfq = float(row["$close"])
            volume = float(row["$volume"])

            # 根据复权类型计算价格
            if adjust == 'qfq' or adjust is None:
                # 前复权: Qlib 原生就是前复权
                open_p, high_p, low_p, close_p = open_qfq, high_qfq, low_qfq, close_qfq
                adjust_factor = factor_val
            elif adjust == 'none':
                # 不复权: 反推原始价格 = 前复权价 / factor
                if factor_val and factor_val > 0:
                    open_p = open_qfq / factor_val
                    high_p = high_qfq / factor_val
                    low_p = low_qfq / factor_val
                    close_p = close_qfq / factor_val
                else:
                    open_p, high_p, low_p, close_p = open_qfq, high_qfq, low_qfq, close_qfq
                adjust_factor = None
            elif adjust == 'hfq':
                # 后复权: Qlib 不直接支持，返回不复权替代
                if factor_val and factor_val > 0:
                    open_p = open_qfq / factor_val
                    high_p = high_qfq / factor_val
                    low_p = low_qfq / factor_val
                    close_p = close_qfq / factor_val
                else:
                    open_p, high_p, low_p, close_p = open_qfq, high_qfq, low_qfq, close_qfq
                adjust_factor = None
            else:
                open_p, high_p, low_p, close_p = open_qfq, high_qfq, low_qfq, close_qfq
                adjust_factor = factor_val

            # Volume 处理
            vol = volume if not math.isnan(volume) else 0.0

            results.append(KlineData(
                date=date_str,
                open=round(open_p, 2),
                high=round(high_p, 2),
                low=round(low_p, 2),
                close=round(close_p, 2),
                volume=int(vol),
                amount=0.0,  # Qlib 没有成交额字段
                adjust_factor=round(adjust_factor, 6) if adjust_factor else None
            ))

        return results

    def kline(self,
              symbol: str,
              period: str = 'day',
              count: int = 30,
              start_date: str = None,
              end_date: str = None) -> Optional[List[KlineData]]:
        """
        获取 K 线数据（前复权）

        Args:
            symbol: 股票代码 (SH600519, SZ000001 等)
            period: 周期 (仅支持 'day')
            count: 获取条数
            start_date: 开始日期 (YYYYMMDD 或 YYYY-MM-DD)
            end_date: 结束日期 (YYYYMMDD 或 YYYY-MM-DD)

        Returns:
            KlineData 列表或 None
        """
        if period != 'day':
            return None

        qlib_symbol = self._symbol_to_qlib(symbol)
        if qlib_symbol is None:
            return None

        fields = ["$open", "$high", "$low", "$close", "$volume", "$factor"]
        start = self._convert_date(start_date) if start_date else None
        end = self._convert_date(end_date) if end_date else None

        df = self._fetch_kline_df(qlib_symbol, fields, start_time=start, end_time=end)
        if df is None:
            return None

        return self._df_to_klines(df, adjust='qfq', count=count)

    def kline_adjusted(self,
                       symbol: str,
                       period: str = 'day',
                       adjust: str = 'qfq') -> Optional[List[KlineData]]:
        """
        获取复权 K 线数据

        Args:
            symbol: 股票代码
            period: 周期
            adjust: 'qfq'前复权, 'hfq'后复权, 'none'不复权
        """
        if period != 'day':
            return None

        qlib_symbol = self._symbol_to_qlib(symbol)
        if qlib_symbol is None:
            return None

        fields = ["$open", "$high", "$low", "$close", "$volume", "$factor"]
        df = self._fetch_kline_df(qlib_symbol, fields)
        if df is None:
            return None

        return self._df_to_klines(df, adjust=adjust)

    def get_latest_price(self, symbol: str) -> Optional[float]:
        """获取最新收盘价（前复权）"""
        qlib_symbol = self._symbol_to_qlib(symbol)
        if qlib_symbol is None:
            return None

        df = self._fetch_kline_df(qlib_symbol, ["$close"])
        if df is None or df.empty:
            return None

        last_close = float(df.iloc[-1]["$close"])
        return last_close

    def get_date_range(self, symbol: str) -> Optional[tuple]:
        """获取数据日期范围"""
        qlib_symbol = self._symbol_to_qlib(symbol)
        if qlib_symbol is None:
            return None

        df = self._fetch_kline_df(qlib_symbol, ["$close"])
        if df is None or df.empty:
            return None

        dates = df.index.get_level_values("datetime")
        start = dates.min().strftime("%Y-%m-%d")
        end = dates.max().strftime("%Y-%m-%d")
        return (start, end)

    def batch_kline(self,
                    symbols: List[str],
                    period: str = 'day',
                    count: int = 30,
                    start_date: str = None,
                    end_date: str = None) -> Dict[str, List[KlineData]]:
        """
        批量获取 K 线数据

        注意：Qlib 的 D.features 支持多股票同时查询，
        但当前实现逐个调用以保持接口一致性
        """
        if period != 'day':
            return {}

        results = {}
        for symbol in symbols:
            klines = self.kline(symbol, period, count, start_date, end_date)
            if klines:
                results[symbol] = klines
        return results

    def close(self):
        """无资源需要关闭"""
        pass


# 全局实例
_qlib_provider: Optional[QlibProvider] = None


def get_qlib_provider() -> QlibProvider:
    """获取全局 QlibProvider 实例"""
    global _qlib_provider
    if _qlib_provider is None:
        _qlib_provider = QlibProvider()
    return _qlib_provider


if __name__ == '__main__':
    # 测试
    print("Testing QlibProvider (direct integration)...")

    provider = QlibProvider()

    if provider.is_available():
        print(f"\nQlibProvider 可用")

        # 测试A股日线
        print("\n=== A股日线 (SH600519 茅台, 前复权) ===")
        klines = provider.kline('SH600519', count=5)
        if klines:
            for k in klines:
                print(f"  {k.date}: O={k.open:.2f} H={k.high:.2f} L={k.low:.2f} C={k.close:.2f} V={k.volume} factor={k.adjust_factor}")

        print("\n=== A股日线 (SH600519 茅台, 不复权) ===")
        klines = provider.kline_adjusted('SH600519', adjust='none')
        if klines:
            for k in klines[-3:]:
                print(f"  {k.date}: O={k.open:.2f} H={k.high:.2f} L={k.low:.2f} C={k.close:.2f} V={k.volume}")

        # 测试日期范围
        print("\n=== 日期范围 ===")
        date_range = provider.get_date_range('SH600519')
        if date_range:
            print(f"  SH600519: {date_range[0]} ~ {date_range[1]}")

        # 测试最新价格
        print("\n=== 最新价格 ===")
        price = provider.get_latest_price('SH600519')
        if price:
            print(f"  SH600519: {price:.2f}")

        # 测试港股（应返回 None）
        print("\n=== 港股测试 (HK00700) ===")
        klines = provider.kline('HK00700')
        print(f"  结果: {klines}")
    else:
        print("QlibProvider 不可用")

    print("\n测试完成!")
