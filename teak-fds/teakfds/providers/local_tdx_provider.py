#!/usr/bin/env python3
"""
LocalTdxProvider - 本地TDX数据库Provider
提供基于本地tdx.db的历史日线查询，支持A股/港股通/指数

数据来源: /Users/Think/agents_documents/tdx_data/tdx.db
"""

import sys
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime

# 添加路径
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from teakfds.providers.base_provider import HistoricalProvider, ProviderCapabilities, ProviderStatus
from teakfds.models import (
    KlineData,
    normalize_symbol,
    detect_market
)
from teakfds.datasource_log import log_info, log_warn, log_error

# 默认数据库路径
DEFAULT_TDX_DB_PATH = '/Users/Think/agents_documents/tdx_data/tdx.db'


class LocalTdxProvider(HistoricalProvider):
    """
    本地TDX数据库Provider
    
    特点:
    - 本地SQLite数据库，无网络延迟
    - 支持A股日线（含复权）
    - 支持港股通日线
    - 支持指数日线
    - 数据稳定可靠
    """
    
    name = "local_tdx"
    display_name = "本地TDX数据库"
    priority = 150  # 本地数据源优先级最高（超过在线源）
    
    capabilities = ProviderCapabilities(
        supports_kline=True,
        supports_financial=False,
        markets=['a_share', 'hk'],
        kline_periods=['day']  # 仅支持日线
    )
    
    def __init__(self, db_path: str = None):
        super().__init__()
        self.db_path = db_path or os.environ.get('TDX_DB_PATH', DEFAULT_TDX_DB_PATH)
        self._conn = None
        self._available = False
        
    def _get_connection(self):
        """获取数据库连接"""
        if self._conn is not None:
            return self._conn
            
        if not os.path.exists(self.db_path):
            log_warn(f"TDX数据库不存在: {self.db_path}")
            return None
            
        try:
            import sqlite3
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._available = True
            log_info(f"LocalTdxProvider 已连接: {self.db_path}")
            return self._conn
        except Exception as e:
            log_error(f"LocalTdxProvider 连接失败: {e}")
            return None
    
    def is_available(self) -> bool:
        """检查Provider是否可用"""
        if self._available and self._conn is not None:
            return True
        conn = self._get_connection()
        return conn is not None
    
    def get_status(self) -> ProviderStatus:
        """获取Provider状态"""
        return ProviderStatus(
            name=self.name,
            available=self.is_available(),
            last_success=datetime.now().isoformat() if self.is_available() else None
        )
    
    def _parse_code(self, symbol: str) -> tuple:
        """
        解析代码格式，返回 (code, market, table)
        
        注意：统一输出小写前缀，与数据库存储格式一致
        
        Returns:
            (code, market, table)
            - code: 数据库中的代码格式（统一小写前缀）
            - market: 'a_share' / 'hk' / 'index'
            - table: 表名 'stock_daily' / 'hk_daily' / 'index_daily'
        """
        market = detect_market(symbol)
        
        if market == 'a_share':
            # A股代码格式: SH600519 -> sh600519（统一小写）
            code = normalize_symbol(symbol, 'tdx')  # 纯数字
            # 确定市场前缀（统一小写）
            if symbol.upper().startswith('SH') or (symbol.upper().endswith('.SH')):
                market_prefix = 'sh'
            elif symbol.upper().startswith('SZ') or (symbol.upper().endswith('.SZ')):
                market_prefix = 'sz'
            elif symbol.upper().startswith('BJ') or (symbol.upper().endswith('.BJ')):
                market_prefix = 'bj'
            elif '.' in symbol:
                # 600519.SH 格式
                parts = symbol.split('.')
                market_prefix = parts[1].lower()
            else:
                # 根据代码推断
                if code.startswith(('6', '5', '9')):
                    market_prefix = 'sh'
                else:
                    market_prefix = 'sz'
            db_code = f"{market_prefix}{code}"
            return db_code, 'a_share', 'stock_daily'
            
        elif market == 'hk':
            # 港股代码格式: HK00700 -> 31#00700
            code = normalize_symbol(symbol, 'standard')
            if code.startswith('HK'):
                code = code[2:]
            # tdx.db中港股格式: 31#00700 或 49#00700
            # 先尝试 31#（港股通）
            db_code = f"31#{code}"
            return db_code, 'hk', 'hk_daily'
            
        else:
            # 指数或未知
            code = normalize_symbol(symbol, 'tdx')
            if symbol.upper().startswith('SH') or symbol.upper().endswith('.SH'):
                market_prefix = 'sh'
            elif symbol.upper().startswith('SZ') or symbol.upper().endswith('.SZ'):
                market_prefix = 'sz'
            else:
                market_prefix = 'sh'
            db_code = f"{market_prefix}{code}"
            return db_code, 'index', 'index_daily'
    
    def _row_to_kline(self, row: dict, adjust: str = None) -> KlineData:
        """
        将数据库行转换为KlineData
        
        Args:
            row: 数据库行
            adjust: 'qfq'前复权, 'hfq'后复权, None不复权
        """
        # 日期格式转换: 20260417 -> 2026-04-17
        date_val = row['date']
        # date可能是整数或字符串，统一转字符串
        date_str_raw = str(date_val)
        date_str = f"{date_str_raw[:4]}-{date_str_raw[4:6]}-{date_str_raw[6:8]}"
        
        open_price = float(row['open'])
        high_price = float(row['high'])
        low_price = float(row['low'])
        close_price = float(row['close'])
        volume = int(row['volume'])
        amount = float(row['amount'])
        
        # 复权处理
        adjust_factor = None
        if adjust and 'qfq' in row and row['qfq'] is not None:
            # 前复权
            if adjust == 'qfq':
                factor = float(row['qfq'])
                open_price = open_price * factor
                high_price = high_price * factor
                low_price = low_price * factor
                close_price = close_price * factor
                adjust_factor = factor
            elif adjust == 'hfq' and 'hfq' in row and row['hfq'] is not None:
                factor = float(row['hfq'])
                open_price = open_price * factor
                high_price = high_price * factor
                low_price = low_price * factor
                close_price = close_price * factor
                adjust_factor = factor
        
        return KlineData(
            date=date_str,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=volume,
            amount=amount,
            adjust_factor=adjust_factor
        )
    
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
            period: 周期 (仅支持 'day')
            count: 获取条数
            start_date: 开始日期 (YYYYMMDD 或 YYYY-MM-DD)
            end_date: 结束日期 (YYYYMMDD 或 YYYY-MM-DD)
        
        Returns:
            KlineData 列表或None
        """
        if period != 'day':
            # 仅支持日线
            return None
            
        conn = self._get_connection()
        if conn is None:
            return None
        
        try:
            db_code, market, table = self._parse_code(symbol)
            
            # 构建SQL查询
            sql = f"SELECT * FROM {table} WHERE code = ?"
            params = [db_code]
            
            # 日期范围
            if start_date:
                start_date = start_date.replace('-', '')
                sql += " AND date >= ?"
                params.append(int(start_date))
            
            if end_date:
                end_date = end_date.replace('-', '')
                sql += " AND date <= ?"
                params.append(int(end_date))
            
            sql += " ORDER BY date DESC"
            
            if count:
                sql += f" LIMIT {count}"
            
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            if not rows:
                return None
            
            # 转换为KlineData
            results = []
            for row in rows:
                row_dict = dict(row)
                kline = self._row_to_kline(row_dict)
                results.append(kline)
            
            # 按日期升序排列（从旧到新）
            results.reverse()
            return results
            
        except Exception as e:
            log_error(f"LocalTdxProvider.kline error for {symbol}: {e}")
            return None
    
    def kline_adjusted(self,
                       symbol: str,
                       period: str = 'day',
                       adjust: str = 'qfq') -> Optional[List[KlineData]]:
        """
        获取复权K线
        
        Args:
            symbol: 股票代码
            period: 周期
            adjust: 'qfq'前复权, 'hfq'后复权, 'none'不复权
        """
        if period != 'day':
            return None
            
        conn = self._get_connection()
        if conn is None:
            return None
        
        try:
            db_code, market, table = self._parse_code(symbol)
            
            # 港股没有复权数据
            if market == 'hk':
                return self.kline(symbol, period)
            
            sql = f"SELECT * FROM {table} WHERE code = ? ORDER BY date DESC LIMIT 500"
            cursor = conn.cursor()
            cursor.execute(sql, [db_code])
            rows = cursor.fetchall()
            
            if not rows:
                return None
            
            results = []
            for row in rows:
                row_dict = dict(row)
                kline = self._row_to_kline(row_dict, adjust=adjust)
                results.append(kline)
            
            results.reverse()
            return results
            
        except Exception as e:
            log_error(f"LocalTdxProvider.kline_adjusted error for {symbol}: {e}")
            return None
    
    def batch_kline(self,
                    symbols: List[str],
                    period: str = 'day',
                    count: int = 30,
                    start_date: str = None,
                    end_date: str = None) -> Dict[str, List[KlineData]]:
        """
        批量获取K线数据
        
        Args:
            symbols: 股票代码列表
            period: 周期
            count: 获取条数
            start_date: 开始日期
            end_date: 结束日期
        
        Returns:
            {symbol: [KlineData]} 字典
        """
        if period != 'day':
            return {}
            
        results = {}
        for symbol in symbols:
            klines = self.kline(symbol, period, count, start_date, end_date)
            if klines:
                results[symbol] = klines
        return results
    
    def get_latest_price(self, symbol: str) -> Optional[float]:
        """
        获取最新收盘价
        
        Args:
            symbol: 股票代码
        
        Returns:
            最新收盘价或None
        """
        conn = self._get_connection()
        if conn is None:
            return None
        
        try:
            db_code, market, table = self._parse_code(symbol)
            sql = f"SELECT close FROM {table} WHERE code = ? ORDER BY date DESC LIMIT 1"
            cursor = conn.cursor()
            cursor.execute(sql, [db_code])
            row = cursor.fetchone()
            
            if row:
                return float(row['close'])
            return None
            
        except Exception as e:
            log_error(f"LocalTdxProvider.get_latest_price error for {symbol}: {e}")
            return None
    
    def get_date_range(self, symbol: str) -> Optional[tuple]:
        """
        获取数据日期范围
        
        Args:
            symbol: 股票代码
        
        Returns:
            (start_date, end_date) 或 None
        """
        conn = self._get_connection()
        if conn is None:
            return None
        
        try:
            db_code, market, table = self._parse_code(symbol)
            sql = f"SELECT MIN(date), MAX(date) FROM {table} WHERE code = ?"
            cursor = conn.cursor()
            cursor.execute(sql, [db_code])
            row = cursor.fetchone()
            
            if row and row[0] and row[1]:
                min_date = str(row[0])
                max_date = str(row[1])
                # 格式化: 20260417 -> 2026-04-17
                min_str = f"{min_date[:4]}-{min_date[4:6]}-{min_date[6:8]}"
                max_str = f"{max_date[:4]}-{max_date[4:6]}-{max_date[6:8]}"
                return (min_str, max_str)
            return None
            
        except Exception as e:
            log_error(f"LocalTdxProvider.get_date_range error for {symbol}: {e}")
            return None
    
    def close(self):
        """关闭数据库连接"""
        if self._conn:
            try:
                self._conn.close()
            except:
                pass
            self._conn = None


# 全局实例
_local_tdx_provider: Optional[LocalTdxProvider] = None


def get_local_tdx_provider() -> LocalTdxProvider:
    """获取全局LocalTdxProvider实例"""
    global _local_tdx_provider
    if _local_tdx_provider is None:
        _local_tdx_provider = LocalTdxProvider()
    return _local_tdx_provider


if __name__ == '__main__':
    # 测试
    print("Testing LocalTdxProvider...")
    
    provider = LocalTdxProvider()
    
    if provider.is_available():
        print(f"\n数据库路径: {provider.db_path}")
        
        # 测试A股日线
        print("\n=== A股日线 (SH600519 茅台) ===")
        klines = provider.kline('SH600519', count=5)
        if klines:
            for k in klines:
                print(f"  {k.date}: {k.open:.2f} - {k.high:.2f} - {k.low:.2f} - {k.close:.2f} vol={k.volume}")
        
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
        
        # 测试港股
        print("\n=== 港股日线 (HK00700 腾讯) ===")
        klines = provider.kline('HK00700', count=5)
        if klines:
            for k in klines:
                print(f"  {k.date}: {k.open:.2f} - {k.high:.2f} - {k.low:.2f} - {k.close:.2f}")
        else:
            print("  无数据")
        
        # 测试批量查询
        print("\n=== 批量查询 ===")
        batch = provider.batch_kline(['SH600519', 'SZ000001'], count=3)
        for sym, klines in batch.items():
            print(f"  {sym}: {len(klines)}条")
    else:
        print(f"LocalTdxProvider 不可用: {provider.db_path}")
    
    provider.close()
    print("\n测试完成!")
