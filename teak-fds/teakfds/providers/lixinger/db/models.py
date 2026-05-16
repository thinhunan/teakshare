"""
理杏仁数据 - SQLite 数据库模型
"""

import sqlite3
import os
from datetime import datetime
from typing import Optional, List
from contextlib import contextmanager


class Database:
    """数据库管理类"""

    def __init__(self, db_path: str = 'db/lixinger.db'):
        self.db_path = db_path
        self._ensure_db_dir()
        self._init_tables()

    def _ensure_db_dir(self):
        """确保数据库目录存在"""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)

    def _init_tables(self):
        """初始化数据库表"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 股票基本信息表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS stock_info (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_id TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    code TEXT NOT NULL,
                    exchange TEXT,
                    stock_type TEXT DEFAULT 'company',
                    pe_ttm REAL,
                    d_pe_ttm REAL,
                    pb REAL,
                    pb_wo_gw REAL,
                    ps_ttm REAL,
                    dividend_yield REAL,
                    publish_date TEXT,
                    sample_num INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 每日估值数据表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS daily_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_id TEXT NOT NULL,
                    date TEXT NOT NULL,
                    pe_ttm REAL,
                    d_pe_ttm REAL,
                    pb REAL,
                    pb_wo_gw REAL,
                    ps_ttm REAL,
                    dyr REAL,
                    close_price REAL,
                    lxr_fc_rights REAL,
                    industry_median REAL,
                    mc REAL,
                    ecmc REAL,
                    percentile REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(stock_id, date)
                )
            ''')

            # 指标统计表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS metric_statistics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_id TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    granularity TEXT DEFAULT 'fs',
                    current REAL,
                    current_percentile REAL,
                    percentile_80 REAL,
                    percentile_50 REAL,
                    percentile_20 REAL,
                    max_value REAL,
                    avg_value REAL,
                    min_value REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(stock_id, metric_name, granularity)
                )
            ''')

            # 财报影响表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS report_impacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_id TEXT NOT NULL,
                    date TEXT NOT NULL,
                    report_date TEXT,
                    report_type TEXT,
                    influence_date TEXT,
                    metrics_name TEXT,
                    total_equity REAL,
                    yoy_change REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(stock_id, date, report_type)
                )
            ''')

            # 创建索引
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_daily_stock_date ON daily_metrics(stock_id, date)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_stats_stock ON metric_statistics(stock_id)')

            conn.commit()

    @contextmanager
    def get_connection(self):
        """获取数据库连接上下文管理器"""
        conn = sqlite3.connect(self.db_path, timeout=15.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def save_stock_info(self, data: dict) -> bool:
        """保存股票基本信息"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            cursor.execute('''
                INSERT INTO stock_info
                    (stock_id, name, code, exchange, stock_type, pe_ttm, d_pe_ttm, pb, pb_wo_gw, ps_ttm,
                     dividend_yield, publish_date, sample_num, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(stock_id) DO UPDATE SET
                    name=excluded.name,
                    code=excluded.code,
                    exchange=excluded.exchange,
                    stock_type=excluded.stock_type,
                    pe_ttm=excluded.pe_ttm,
                    d_pe_ttm=excluded.d_pe_ttm,
                    pb=excluded.pb,
                    pb_wo_gw=excluded.pb_wo_gw,
                    ps_ttm=excluded.ps_ttm,
                    dividend_yield=excluded.dividend_yield,
                    publish_date=excluded.publish_date,
                    sample_num=excluded.sample_num,
                    updated_at=excluded.updated_at
            ''', (
                data.get('stock_id'),
                data.get('name'),
                data.get('code'),
                data.get('exchange'),
                data.get('stock_type', 'company'),
                data.get('pe_ttm'),
                data.get('d_pe_ttm'),
                data.get('pb'),
                data.get('pb_wo_gw'),
                data.get('ps_ttm'),
                data.get('dividend_yield'),
                data.get('publish_date'),
                data.get('sample_num'),
                now
            ))
            conn.commit()
            return True

    def save_daily_metrics(self, stock_id: str, daily_data: List[dict]) -> int:
        """保存每日估值数据，返回插入/更新的记录数"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            count = 0

            for item in daily_data:
                cursor.execute('''
                    INSERT INTO daily_metrics
                        (stock_id, date, pe_ttm, d_pe_ttm, pb, pb_wo_gw, ps_ttm, dyr,
                         close_price, lxr_fc_rights, industry_median, mc, ecmc, percentile)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(stock_id, date) DO UPDATE SET
                        pe_ttm=excluded.pe_ttm,
                        d_pe_ttm=excluded.d_pe_ttm,
                        pb=excluded.pb,
                        pb_wo_gw=excluded.pb_wo_gw,
                        ps_ttm=excluded.ps_ttm,
                        dyr=excluded.dyr,
                        close_price=excluded.close_price,
                        lxr_fc_rights=excluded.lxr_fc_rights,
                        industry_median=excluded.industry_median,
                        mc=excluded.mc,
                        ecmc=excluded.ecmc,
                        percentile=excluded.percentile
                ''', (
                    stock_id,
                    item.get('date'),
                    item.get('pe_ttm'),
                    item.get('d_pe_ttm'),
                    item.get('pb'),
                    item.get('pb_wo_gw'),
                    item.get('ps_ttm'),
                    item.get('dyr'),
                    item.get('close_price'),
                    item.get('lxr_fc_rights'),
                    item.get('industry_median'),
                    item.get('mc'),
                    item.get('ecmc'),
                    item.get('percentile')
                ))
                count += 1

            conn.commit()
            return count

    def save_metric_statistics(self, stock_id: str, metric_name: str, stats: dict, granularity: str = 'fs') -> bool:
        """保存指标统计数据"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            cursor.execute('''
                INSERT INTO metric_statistics
                    (stock_id, metric_name, granularity, current, current_percentile,
                     percentile_80, percentile_50, percentile_20, max_value, avg_value, min_value, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(stock_id, metric_name, granularity) DO UPDATE SET
                    current=excluded.current,
                    current_percentile=excluded.current_percentile,
                    percentile_80=excluded.percentile_80,
                    percentile_50=excluded.percentile_50,
                    percentile_20=excluded.percentile_20,
                    max_value=excluded.max_value,
                    avg_value=excluded.avg_value,
                    min_value=excluded.min_value,
                    updated_at=excluded.updated_at
            ''', (
                stock_id,
                metric_name,
                granularity,
                stats.get('current'),
                stats.get('current_percentile'),
                stats.get('percentile_80'),
                stats.get('percentile_50'),
                stats.get('percentile_20'),
                stats.get('max_value'),
                stats.get('avg_value'),
                stats.get('min_value'),
                now
            ))
            conn.commit()
            return True

    def save_report_impacts(self, stock_id: str, impacts: List[dict]) -> int:
        """保存财报影响数据"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            count = 0

            for item in impacts:
                cursor.execute('''
                    INSERT INTO report_impacts
                        (stock_id, date, report_date, report_type, influence_date,
                         metrics_name, total_equity, yoy_change)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(stock_id, date, report_type) DO UPDATE SET
                        report_date=excluded.report_date,
                        influence_date=excluded.influence_date,
                        metrics_name=excluded.metrics_name,
                        total_equity=excluded.total_equity,
                        yoy_change=excluded.yoy_change
                ''', (
                    stock_id,
                    item.get('date'),
                    item.get('report_date'),
                    item.get('report_type'),
                    item.get('influence_date'),
                    item.get('metrics_name'),
                    item.get('total_equity'),
                    item.get('yoy_change')
                ))
                count += 1

            conn.commit()
            return count

    def save_comprehensive_data(self, data, granularity: str = 'fs', stock_type: str = 'company') -> dict:
        """
        保存完整数据到数据库

        Args:
            data: ComprehensiveData 对象
            granularity: 时间粒度
            stock_type: 股票类型 (company/index)

        Returns:
            保存结果统计
        """
        result = {
            'stock_info': False,
            'daily_count': 0,
            'stats_saved': 0,
            'impact_count': 0
        }

        if not data or not data.stock_info:
            return result

        stock_id = data.stock_info.stock_id

        # 1. 保存基本信息
        info_dict = data.stock_info.to_dict()
        info_dict['stock_type'] = stock_type
        result['stock_info'] = self.save_stock_info(info_dict)

        # 2. 保存每日数据
        daily_list = [d.to_dict() for d in data.daily_data]
        result['daily_count'] = self.save_daily_metrics(stock_id, daily_list)

        # 3. 保存统计数据
        for name, stats in [
            ('pe_ttm', data.pe_stats),
            ('pb', data.pb_stats),
            ('ps_ttm', data.ps_stats),
            ('dyr', data.dyr_stats)
        ]:
            if stats:
                self.save_metric_statistics(stock_id, name, stats.to_dict(), granularity)
                result['stats_saved'] += 1

        # 4. 保存财报影响
        impact_list = [r.to_dict() for r in data.report_impacts]
        result['impact_count'] = self.save_report_impacts(stock_id, impact_list)

        return result

    def get_stock_info(self, code: str) -> Optional[dict]:
        """根据代码查询股票信息"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM stock_info WHERE code = ?', (code,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_stock_info_by_stock_id(self, stock_id: str) -> Optional[dict]:
        """根据 stock_id 查询股票信息"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM stock_info WHERE stock_id = ?', (stock_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_daily_metrics(self, stock_id: str, limit: int = None) -> List[dict]:
        """查询每日数据"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if limit:
                cursor.execute(
                    'SELECT * FROM daily_metrics WHERE stock_id = ? ORDER BY date DESC LIMIT ?',
                    (stock_id, limit)
                )
            else:
                cursor.execute(
                    'SELECT * FROM daily_metrics WHERE stock_id = ? ORDER BY date DESC',
                    (stock_id,)
                )
            return [dict(row) for row in cursor.fetchall()]

    def get_latest_daily_metric(self, stock_id: str) -> Optional[dict]:
        """获取最新一条每日数据"""
        rows = self.get_daily_metrics(stock_id, limit=1)
        return rows[0] if rows else None

    def get_metric_statistics(self, stock_id: str, granularity: str = 'fs') -> List[dict]:
        """查询指标统计"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM metric_statistics WHERE stock_id = ? AND granularity = ?',
                (stock_id, granularity)
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_report_impacts(self, stock_id: str, limit: int = None) -> List[dict]:
        """查询财报影响数据"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if limit:
                cursor.execute(
                    'SELECT * FROM report_impacts WHERE stock_id = ? ORDER BY date DESC LIMIT ?',
                    (stock_id, limit)
                )
            else:
                cursor.execute(
                    'SELECT * FROM report_impacts WHERE stock_id = ? ORDER BY date DESC',
                    (stock_id,)
                )
            return [dict(row) for row in cursor.fetchall()]

    def get_all_stocks(self) -> List[dict]:
        """获取所有已保存的股票列表"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM stock_info ORDER BY updated_at DESC')
            return [dict(row) for row in cursor.fetchall()]

    def has_stock_data(self, stock_id: str, min_records: int = 100) -> bool:
        """
        检查是否已有足够的历史数据
        
        Args:
            stock_id: 股票ID
            min_records: 最小记录数，超过这个数认为已有完整数据
            
        Returns:
            是否已有足够数据
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT COUNT(*) as cnt FROM daily_metrics WHERE stock_id = ?',
                (stock_id,)
            )
            result = cursor.fetchone()
            return result['cnt'] >= min_records

    def get_latest_date(self, stock_id: str) -> Optional[str]:
        """获取最新数据日期"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT MAX(date) as latest FROM daily_metrics WHERE stock_id = ?',
                (stock_id,)
            )
            result = cursor.fetchone()
            return result['latest'] if result else None

    def get_data_summary(self, stock_id: str) -> dict:
        """获取数据概要"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 总记录数
            cursor.execute(
                'SELECT COUNT(*) as cnt FROM daily_metrics WHERE stock_id = ?',
                (stock_id,)
            )
            total = cursor.fetchone()['cnt']
            
            # 日期范围
            cursor.execute('''
                SELECT MIN(date) as min_date, MAX(date) as max_date 
                FROM daily_metrics WHERE stock_id = ?
            ''', (stock_id,))
            date_range = cursor.fetchone()
            
            return {
                'stock_id': stock_id,
                'total_records': total,
                'min_date': date_range['min_date'],
                'max_date': date_range['max_date'],
                'has_full_data': total >= 100  # 超过100条认为有完整数据
            }

    def delete_stock_data(self, stock_id: str) -> dict:
        """删除股票相关的所有数据"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('DELETE FROM daily_metrics WHERE stock_id = ?', (stock_id,))
            daily_deleted = cursor.rowcount

            cursor.execute('DELETE FROM metric_statistics WHERE stock_id = ?', (stock_id,))
            stats_deleted = cursor.rowcount

            cursor.execute('DELETE FROM report_impacts WHERE stock_id = ?', (stock_id,))
            impact_deleted = cursor.rowcount

            cursor.execute('DELETE FROM stock_info WHERE stock_id = ?', (stock_id,))
            info_deleted = cursor.rowcount

            conn.commit()

            return {
                'stock_info': info_deleted,
                'daily_metrics': daily_deleted,
                'statistics': stats_deleted,
                'impacts': impact_deleted
            }
