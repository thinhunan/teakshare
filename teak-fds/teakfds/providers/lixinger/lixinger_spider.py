"""
理杏仁(lixinger.com) 数据爬虫
用于获取指数和公司估值数据（PE、PB、PS、股息率等）
支持数据保存到 SQLite 数据库
"""

import requests
from teakfds.datasource_log import log_info, log_warn, log_error
import json
import os
import sys
import time
from dataclasses import dataclass, asdict, field, replace
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta

# 添加项目根目录到 Python 路径
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_SCRIPTS_ROOT = os.path.dirname(_PROJECT_ROOT)
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)
from teakfds.datasource_log import log_external_request  # noqa: E402

# 使用相对导入
from .db import Database


@dataclass
class StockInfo:
    """股票基本信息"""
    stock_id: str
    name: str
    code: str
    exchange: str
    pe_ttm: float
    d_pe_ttm: float  # 扣非PE
    pb: float
    pb_wo_gw: float  # 不含商誉PB
    ps_ttm: float
    dividend_yield: float
    publish_date: str
    sample_num: int
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class MetricValue:
    """单个指标在某日期的值"""
    date: str
    value: float
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class DailyMetrics:
    """某日的所有指标数据"""
    date: str
    # 估值指标
    pe_ttm: Optional[float] = None
    d_pe_ttm: Optional[float] = None  # 扣非PE
    pb: Optional[float] = None
    pb_wo_gw: Optional[float] = None  # 不含商誉PB
    ps_ttm: Optional[float] = None
    dyr: Optional[float] = None  # 股息率
    # 价格指标
    close_price: Optional[float] = None
    lxr_fc_rights: Optional[float] = None  # 理杏仁前复权
    industry_median: Optional[float] = None  # 行业中位数
    mc: Optional[float] = None  # 市值
    ecmc: Optional[float] = None  # 自由流通市值
    # 分位点
    percentile: Optional[float] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class MetricStatistics:
    """单个指标的统计数据"""
    name: str
    current: float
    current_percentile: float
    percentile_80: float
    percentile_50: float
    percentile_20: float
    max_value: float
    avg_value: float
    min_value: float
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ReportImpact:
    """财报发布对估值的影响"""
    date: str
    report_date: str
    report_type: str
    influence_date: str
    metrics_name: str
    total_equity: float  # 总权益 (亿元)
    yoy_change: float     # 同比变化率
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class FinancialMetrics:
    """财务报表指标"""
    date: str
    report_date: str
    report_type: str
    standard_date: str
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ComprehensiveData:
    """完整的多指标估值数据"""
    stock_info: StockInfo
    daily_data: List[DailyMetrics]  # 每日完整数据
    # 各指标统计
    pe_stats: Optional[MetricStatistics] = None
    pb_stats: Optional[MetricStatistics] = None
    ps_stats: Optional[MetricStatistics] = None
    dyr_stats: Optional[MetricStatistics] = None
    # 其他数据
    report_impacts: List[ReportImpact] = field(default_factory=list)
    financial_metrics: List[FinancialMetrics] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            'stock_info': self.stock_info.to_dict(),
            'daily_data': [d.to_dict() for d in self.daily_data],
            'pe_stats': self.pe_stats.to_dict() if self.pe_stats else None,
            'pb_stats': self.pb_stats.to_dict() if self.pb_stats else None,
            'ps_stats': self.ps_stats.to_dict() if self.ps_stats else None,
            'dyr_stats': self.dyr_stats.to_dict() if self.dyr_stats else None,
            'report_impacts': [r.to_dict() for r in self.report_impacts],
            'financial_metrics': [f.to_dict() for f in self.financial_metrics]
        }


@dataclass
class ScreenerStock:
    """筛选结果中的股票信息"""
    stock_id: str
    name: str
    code: str
    exchange: str
    market: str
    area_code: str
    industry_name: str
    industry_level: str
    ipo_date: str
    # 估值分位数据
    pb_percentile: float  # PB历史分位
    pe_percentile: float  # PE历史分位
    ps_percentile: float  # PS历史分位
    dyr_percentile: float  # 股息率历史分位
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class UndervaluedScreenerResult:
    """低估股票筛选结果"""
    total: int
    stocks: List[ScreenerStock]
    area_code: str
    filter_params: Dict
    
    def to_dict(self) -> Dict:
        return {
            'total': self.total,
            'stocks': [s.to_dict() for s in self.stocks],
            'area_code': self.area_code,
            'filter_params': self.filter_params
        }


class LixingerSpider:
    """理杏仁数据爬虫 - 支持多指标全面获取"""
    
    # 公司类型支持的多指标（可一次请求）
    COMPANY_LEFT_METRICS = ["d_pe_ttm", "pe_ttm", "pb", "pb_wo_gw", "ps_ttm", "dyr"]
    COMPANY_RIGHT_METRICS = ["lxr_fc_rights", "sp", "mc", "ecmc", "industry_median_value"]
    
    # 指数类型支持的指标（需分批请求）
    INDEX_METRICS = ["pe_ttm", "pb", "ps_ttm", "dyr"]
    
    def __init__(self, settings_path: str = 'settings.json', cookie_path: str = 'cookie.txt', 
                 db_path: str = 'db/lixinger.db', auto_save: bool = False, 
                 force_use_cookie: bool = False):
        """
        初始化爬虫
        
        Args:
            settings_path: 配置文件路径
            cookie_path: Cookie文件路径
            db_path: 数据库文件路径
            auto_save: 是否自动保存数据到数据库
            force_use_cookie: 是否强制使用现有cookie（即使过期），请求失败时再重新登录
        """
        self.settings = self._load_settings(settings_path)
        self.cookie_path = cookie_path
        self.session = requests.Session()
        self.auto_save = auto_save
        self.force_use_cookie = force_use_cookie
        self.last_error = None
        self.db = Database(db_path) if db_path else None
        
        headers = self.settings['headers'].copy()
        cookie = self._load_cookie(cookie_path)
        
        # 如果cookie不存在或已过期（且不是强制模式）
        if cookie is None:
            if force_use_cookie:
                # 强制模式：尝试读取任何存在的cookie
                cookie = self._read_cookie_anyway(cookie_path)
                if cookie:
                    log_info(f"📌 强制使用现有Cookie（可能已过期，请求失败时会重新登录）")
            
            if cookie is None:
                cookie = self._auto_login()
                if cookie:
                    self._save_cookie(cookie_path, cookie)
        
        if cookie is None:
            raise ValueError("无法获取Cookie，请检查登录配置或手动创建cookie.txt")
        
        headers['cookie'] = cookie
        self.session.headers.update(headers)
    
    def _read_cookie_anyway(self, path: str) -> Optional[str]:
        """不管是否过期，直接读取cookie"""
        try:
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read().strip()
        except Exception:
            pass
        return None
    
    def _save_cookie(self, path: str, cookie: str):
        """保存cookie到文件"""
        with open(path, 'w', encoding='utf-8') as f:
            f.write(cookie)
        print(f"✅ Cookie已保存到: {path}")
    
    def _refresh_cookie_if_needed(self):
        """刷新过期的cookie"""
        cookie = self._auto_login()
        if cookie:
            self._save_cookie(self.cookie_path, cookie)
            self.session.headers['cookie'] = cookie
            return True
        return False
    
    def _load_cookie(self, path: str) -> str:
        """从文件加载cookie，检查是否过期（1小时）"""
        try:
            # 检查文件修改时间
            if os.path.exists(path):
                mtime = os.path.getmtime(path)
                age = time.time() - mtime
                if age > 3600:  # 超过1小时
                    log_warn(f"⚠️ Cookie已过期（{age/60:.1f}分钟前获取），需要重新登录...")
                    return None
            
            with open(path, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except FileNotFoundError:
            log_warn(f"⚠️ Cookie文件不存在: {path}，尝试自动登录...")
            return None
    
    def _auto_login(self) -> Optional[str]:
        """自动登录获取cookie"""
        req_url = ""
        log_body: Optional[Dict] = None
        try:
            login_config = self.settings['urls'][0]
            url = login_config['url']
            req_url = url
            body = json.loads(login_config['body'])
            log_body = body
            
            log_info(f"🔄 正在登录: {body.get('accountName')}")
            
            headers = self.settings['headers'].copy()
            headers['Content-Type'] = 'application/json'
            
            t0 = time.time()
            response = requests.post(url, json=body, headers=headers, timeout=30)
            elapsed_ms = (time.time() - t0) * 1000
            log_external_request(
                provider="lixinger",
                method="POST",
                url=str(response.url),
                action="login",
                success=response.status_code == 200,
                status_code=response.status_code,
                duration_ms=elapsed_ms,
                message="auto_login",
                params=log_body,
                caller="LixingerSpider._auto_login",
            )

            if response.status_code == 200:
                # 1) 优先从 Set-Cookie 提取 jwt
                set_cookie = response.headers.get('Set-Cookie')
                if set_cookie:
                    import re
                    match = re.search(r'jwt=([^;]+)', set_cookie)
                    if match:
                        jwt_token = match.group(1)
                        cookie = f"jwt={jwt_token}"
                        print("✅ 自动登录成功")
                        return cookie

                # 2) 从 response.cookies 回退提取
                jwt_from_cookie = response.cookies.get('jwt')
                if jwt_from_cookie:
                    cookie = f"jwt={jwt_from_cookie}"
                    print("✅ 自动登录成功")
                    return cookie

                # 3) 从响应体回退提取
                try:
                    resp_json = response.json()
                    token = (
                        resp_json.get('jwt')
                        or resp_json.get('token')
                        or resp_json.get('data', {}).get('jwt')
                        or resp_json.get('data', {}).get('token')
                    )
                    if token:
                        cookie = f"jwt={token}"
                        print("✅ 自动登录成功")
                        return cookie
                except Exception:
                    pass
            
            log_error(f"❌ 自动登录失败: {response.status_code}")
            return None
            
        except Exception as e:
            log_error(f"❌ 自动登录出错: {e}")
            log_external_request(
                provider="lixinger",
                method="POST",
                url=req_url or "login",
                action="login",
                success=False,
                message=str(e)[:800],
                params=log_body,
                caller="LixingerSpider._auto_login",
            )
            return None
    
    def _load_settings(self, path: str) -> Dict:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _request(self, url: str, method: str = 'GET', body: Optional[Dict] = None, 
                 retry_on_auth_fail: bool = True) -> Optional[Dict]:
        """
        发送请求
        
        Args:
            url: 请求URL
            method: 请求方法
            body: 请求体
            retry_on_auth_fail: 认证失败时是否重试（重新登录后重试一次）
        """
        self.last_error = None
        t0 = time.time()
        try:
            if method.upper() == 'GET':
                response = self.session.get(url, timeout=30)
            else:
                response = self.session.post(url, json=body, timeout=30)
        except Exception as e:
            log_external_request(
                provider="lixinger",
                method=method.upper(),
                url=url,
                action="api",
                success=False,
                duration_ms=(time.time() - t0) * 1000,
                message=str(e)[:800],
                params=body,
                caller="LixingerSpider._request",
            )
            if retry_on_auth_fail:
                log_warn("⚠️ 请求失败，尝试重新登录并重试一次...")
                if self._refresh_cookie_if_needed():
                    return self._request(url, method, body, retry_on_auth_fail=False)
            self.last_error = f"请求异常: {e}"
            print(f"请求失败: {self.last_error}")
            return None

        elapsed_ms = (time.time() - t0) * 1000
        final_u = str(response.url) if getattr(response, "url", None) else url
        resp_json = None
        try:
            resp_json = response.json()
        except Exception:
            resp_json = None

        # 认证失败检测（HTTP状态码 + 业务错误字段）
        auth_failed = response.status_code in (401, 403)
        if not auth_failed and isinstance(resp_json, dict):
            code = str(resp_json.get('code', '')).lower()
            msg = str(
                resp_json.get('msg')
                or resp_json.get('message')
                or resp_json.get('error')
                or ''
            ).lower()
            auth_keywords = ('登录', '未登录', 'cookie', 'jwt', 'token', 'auth', '权限')
            if code in ('401', '403', 'unauthorized', 'no_auth') or any(k in msg for k in auth_keywords):
                auth_failed = True

        if auth_failed:
            if retry_on_auth_fail:
                log_warn("⚠️ Cookie已失效或认证异常，尝试重新登录并重试一次...")
                if self._refresh_cookie_if_needed():
                    return self._request(url, method, body, retry_on_auth_fail=False)
            self.last_error = f"认证失败: HTTP {response.status_code}"
            print(f"请求失败: {self.last_error}")
            log_external_request(
                provider="lixinger",
                method=method.upper(),
                url=final_u,
                action="api",
                success=False,
                status_code=response.status_code,
                duration_ms=elapsed_ms,
                message=self.last_error,
                params=body,
                caller="LixingerSpider._request",
            )
            return None

        if response.status_code >= 400:
            if retry_on_auth_fail:
                # 按要求：请求失败时允许登录后重试一次
                log_warn("⚠️ 请求失败，尝试重新登录并重试一次...")
                if self._refresh_cookie_if_needed():
                    return self._request(url, method, body, retry_on_auth_fail=False)
            body_preview = response.text[:200] if response.text else ""
            self.last_error = f"HTTP {response.status_code}: {body_preview}"
            print(f"请求失败: {self.last_error}")
            log_external_request(
                provider="lixinger",
                method=method.upper(),
                url=final_u,
                action="api",
                success=False,
                status_code=response.status_code,
                duration_ms=elapsed_ms,
                message=self.last_error,
                params=body,
                caller="LixingerSpider._request",
            )
            return None

        if resp_json is None:
            self.last_error = "响应不是有效JSON"
            print(f"请求失败: {self.last_error}")
            log_external_request(
                provider="lixinger",
                method=method.upper(),
                url=final_u,
                action="api",
                success=False,
                status_code=response.status_code,
                duration_ms=elapsed_ms,
                message=self.last_error or "invalid_json",
                params=body,
                caller="LixingerSpider._request",
            )
            return None
        log_external_request(
            provider="lixinger",
            method=method.upper(),
            url=final_u,
            action="api",
            success=True,
            status_code=response.status_code,
            duration_ms=elapsed_ms,
            message="ok",
            params=body,
            caller="LixingerSpider._request",
        )
        return resp_json
    
    def _get_exchange(self, code: str) -> str:
        """根据代码判断交易所"""
        # 港股：5位数字且以0开头（如00700）
        if len(code) == 5 and code.startswith('0'):
            return 'hk'
        # A股上海
        if code.startswith('6') or code.startswith('5'):
            return 'sh'
        if code in ['000300', '000905', '000001']:
            return 'sh'
        return 'sz'

    def _get_stock_type(self, code: str) -> str:
        """判断是指数(index)还是公司(company)"""
        index_codes = ['000001', '000300', '000905', '000016', '000010']
        if code in index_codes or code.startswith('399') or code.startswith('95') or code.startswith('98'):
            return 'index'
        return 'company'
    
    def _get_api_type(self, code: str) -> str:
        """指数 -> 'ii', 公司 -> 'company'"""
        return 'ii' if self._get_stock_type(code) == 'index' else 'company'
    
    def get_stock_info(self, code: str) -> Optional[StockInfo]:
        """获取股票基本信息"""
        exchange = self._get_exchange(code)
        stock_type = self._get_stock_type(code)
        url_config = self.settings['urls'][1]
        url = url_config['url'].format(Type=stock_type, Market=exchange, StockCode=code)
        data = self._request(url)
        
        if not data:
            return None
        
        stock = data if '_id' in data else data.get('data', {})
        metrics = stock.get('priceMetrics', {})
        
        def get_metric_value(metric_key):
            value = metrics.get(metric_key, 0)
            if isinstance(value, dict):
                return float(value.get('mcw', 0) or 0)
            return float(value or 0)
        
        # 注：港股等标的在详情接口的 priceMetrics 里，部分指标可能缺失或非 mcw 嵌套，
        # get_metric_value 会得到 0；同次 get-price-metrics-chart-info 的 priceMetricsList 日线里仍有正确数值，
        # 见 get_comprehensive_data 末尾 _enrich_stock_info_from_latest_daily。
        return StockInfo(
            stock_id=str(stock.get('_id', '')),
            name=stock.get('name', ''),
            code=stock.get('stockCode', ''),
            exchange=stock.get('exchange', ''),
            pe_ttm=get_metric_value('pe_ttm'),
            d_pe_ttm=get_metric_value('d_pe_ttm'),
            pb=get_metric_value('pb'),
            pb_wo_gw=get_metric_value('pb_wo_gw'),
            ps_ttm=get_metric_value('ps_ttm'),
            dividend_yield=get_metric_value('dyr') * 100,
            publish_date=stock.get('publishDate', ''),
            sample_num=int(stock.get('stocksNum', 0) or 0)
        )

    @staticmethod
    def _enrich_stock_info_from_latest_daily(
        info: StockInfo, daily_data: List[DailyMetrics]
    ) -> StockInfo:
        """
        用 priceMetricsList 最新一行补全 StockInfo 中仍为 0 的估值字段。

        理杏仁「证券详情」与「价格指标图表」数据源不一致时（常见于港股），
        详情里 ps_ttm 等可能为 0，而图表接口日线里字段齐全。
        """
        if not daily_data:
            return info
        latest = daily_data[0]
        updates: Dict[str, float] = {}
        for attr in ("pe_ttm", "d_pe_ttm", "pb", "pb_wo_gw", "ps_ttm"):
            cur = getattr(info, attr, None)
            nv = getattr(latest, attr, None)
            if nv is None:
                continue
            try:
                cf = float(cur or 0)
                nf = float(nv)
            except (TypeError, ValueError):
                continue
            if abs(cf) < 1e-12 and abs(nf) > 1e-12:
                updates[attr] = nf
        # 股息率：StockInfo 存「百分数」口径（与 get_stock_info 中 dyr*100 一致）
        try:
            cur_dy = float(info.dividend_yield or 0)
            ld = latest.dyr
            if ld is not None and abs(cur_dy) < 1e-12:
                raw = float(ld)
                updates["dividend_yield"] = raw * 100.0 if 0.0 <= raw <= 1.0 else raw
        except (TypeError, ValueError):
            pass
        if not updates:
            return info
        return replace(info, **updates)
    
    def _fetch_company_metrics(self, stock_id: str, granularity: str = 'fs') -> Optional[Dict]:
        """获取公司多指标数据（一次性请求）"""
        url_config = self.settings['urls'][2]
        url = url_config['url'].format(Type='company')
        
        body = {
            "stockIds": [int(stock_id)],
            "granularity": granularity,
            "leftMetricsNames": self.COMPANY_LEFT_METRICS,
            "rightMetricsNames": self.COMPANY_RIGHT_METRICS
        }
        return self._request(url, method='POST', body=body)
    
    def _fetch_index_metric(self, stock_id: str, metric: str, granularity: str = 'fs') -> Optional[Dict]:
        """获取指数单个指标数据"""
        url_config = self.settings['urls'][2]
        url = url_config['url'].format(Type='ii')
        
        body = {
            "stockIds": [int(stock_id)],
            "granularity": granularity,
            "metricsTypes": ["mcw"],
            "leftMetricsNames": [metric],
            "rightMetricsNames": ["ecmc"]
        }
        return self._request(url, method='POST', body=body)
    
    def _fetch_index_all_metrics(self, stock_id: str, granularity: str = 'fs') -> Dict[str, Dict]:
        """获取指数所有指标数据（分批请求）"""
        results = {}
        for metric in self.INDEX_METRICS:
            print(f"  获取指数 {metric} 数据...")
            data = self._fetch_index_metric(stock_id, metric, granularity)
            if data:
                results[metric] = data
        return results
    
    def _parse_company_data(self, raw_data: Dict) -> ComprehensiveData:
        """解析公司多指标数据"""
        def safe_float(v, default=0.0):
            try:
                if v is None:
                    return float(default)
                return float(v)
            except (TypeError, ValueError):
                return float(default)

        # 获取日期列表
        price_list = raw_data.get('priceMetricsList', [])
        if not price_list:
            raise ValueError("无价格数据")
        
        # 构建每日数据
        daily_data = []
        for item in price_list:
            date = item.get('date', '')[:10]
            if not date:
                continue
            
            dm = DailyMetrics(date=date)
            
            # 解析leftMetrics（估值指标）
            for metric in ['pe_ttm', 'd_pe_ttm', 'pb', 'pb_wo_gw', 'ps_ttm', 'dyr']:
                value = item.get(metric)
                if value is not None:
                    setattr(dm, metric, safe_float(value))
            
            # 解析rightMetrics（价格和市值）
            dm.close_price = item.get('sp')
            dm.lxr_fc_rights = item.get('lxr_fc_rights')
            dm.industry_median = item.get('industry_median_value')
            dm.mc = item.get('mc')
            dm.ecmc = item.get('ecmc')
            
            # 解析分位点（如果有）
            stats = item.get('statistics', {}).get('pb', {})
            if stats:
                dm.percentile = safe_float(stats.get('cvpos', 0)) * 100
            
            daily_data.append(dm)
        
        # 解析统计数据
        all_stats = raw_data.get('allStatisticsData', {})
        
        def create_stats(metric_name: str) -> Optional[MetricStatistics]:
            stats = all_stats.get(metric_name, {})
            if not stats:
                return None
            return MetricStatistics(
                name=metric_name,
                current=safe_float(stats.get('cv', 0)),
                current_percentile=safe_float(stats.get('cvpos', 0)) * 100,
                percentile_80=safe_float(stats.get('q8v', 0)),
                percentile_50=safe_float(stats.get('q5v', 0)),
                percentile_20=safe_float(stats.get('q2v', 0)),
                max_value=safe_float(stats.get('maxv', 0)),
                avg_value=safe_float(stats.get('avgv', 0)),
                min_value=safe_float(stats.get('minv', 0))
            )
        
        # 解析财报影响
        impacts = []
        for item in raw_data.get('priceMetricsInfluencesList', []):
            q_data = item.get('q', {}).get('bs', {}).get('tetoshopc', {})
            if q_data:
                impacts.append(ReportImpact(
                    date=item.get('date', '')[:10],
                    report_date=item.get('firstReportDate', '')[:10],
                    report_type=item.get('reportType', ''),
                    influence_date=item.get('influenceDate', '')[:10],
                    metrics_name=item.get('metricsName', ''),
                    total_equity=safe_float(q_data.get('t_o', 0)) / 1e8,
                    yoy_change=safe_float(q_data.get('t_y2y', 0))
                ))
        
        # 解析财务指标
        financials = []
        for item in raw_data.get('fsMetricsList', []):
            financials.append(FinancialMetrics(
                date=item.get('date', '')[:10],
                report_date=item.get('reportDate', '')[:10],
                report_type=item.get('reportType', ''),
                standard_date=item.get('standardDate', '')[:10]
            ))
        
        return ComprehensiveData(
            stock_info=None,  # 稍后填充
            daily_data=daily_data,
            pe_stats=create_stats('pe_ttm'),
            pb_stats=create_stats('pb'),
            ps_stats=create_stats('ps_ttm'),
            dyr_stats=create_stats('dyr'),
            report_impacts=impacts,
            financial_metrics=financials
        )
    
    def _parse_index_data(self, raw_data_dict: Dict[str, Dict]) -> ComprehensiveData:
        """解析指数多批次数据并合并"""
        def safe_float(v, default=0.0):
            try:
                if v is None:
                    return float(default)
                return float(v)
            except (TypeError, ValueError):
                return float(default)

        # 使用第一个指标作为基准获取日期列表
        first_metric = list(raw_data_dict.keys())[0]
        base_data = raw_data_dict[first_metric]
        price_list = base_data.get('priceMetricsList', [])
        
        # 建立日期索引
        date_index = {item.get('date', '')[:10]: i for i, item in enumerate(price_list)}
        
        # 构建每日数据
        daily_data = []
        for date, idx in sorted(date_index.items()):
            dm = DailyMetrics(date=date)
            
            # 填充各指标
            for metric, data in raw_data_dict.items():
                price_list = data.get('priceMetricsList', [])
                if idx < len(price_list):
                    item = price_list[idx]
                    # 解析指标值 - 指数格式: {"pb": {"mcw": value}}
                    metric_data = item.get(metric, {})
                    if isinstance(metric_data, dict):
                        value = metric_data.get('mcw')
                    else:
                        value = metric_data
                    
                    if value is not None:
                        setattr(dm, metric, safe_float(value))
                    
                    # 解析ecmc（市值）- 指数格式: {"ecmc": value} 或 {"ecmc": {"mcw": value}}
                    if dm.ecmc is None:
                        ecmc_data = item.get('ecmc')
                        if isinstance(ecmc_data, dict):
                            dm.ecmc = ecmc_data.get('mcw')
                        else:
                            dm.ecmc = ecmc_data
                    
                    # 解析分位点 - 指数格式: {"statistics": {"pb": {"mcw": {"cvpos": 0.76}}}}
                    if dm.percentile is None:
                        stats = item.get('statistics', {}).get(metric, {})
                        if isinstance(stats, dict):
                            if 'mcw' in stats:
                                stats = stats['mcw']
                            dm.percentile = safe_float(stats.get('cvpos', 0)) * 100
            
            daily_data.append(dm)
        
        # 解析统计数据
        def create_stats(metric_name: str) -> Optional[MetricStatistics]:
            if metric_name not in raw_data_dict:
                return None
            all_stats = raw_data_dict[metric_name].get('allStatisticsData', {})
            stats = all_stats.get(metric_name, {})
            if isinstance(stats, dict) and 'mcw' in stats:
                stats = stats['mcw']
            
            if not stats:
                return None
                
            return MetricStatistics(
                name=metric_name,
                current=safe_float(stats.get('cv', 0)),
                current_percentile=safe_float(stats.get('cvpos', 0)) * 100,
                percentile_80=safe_float(stats.get('q8v', 0)),
                percentile_50=safe_float(stats.get('q5v', 0)),
                percentile_20=safe_float(stats.get('q2v', 0)),
                max_value=safe_float(stats.get('maxv', 0)),
                avg_value=safe_float(stats.get('avgv', 0)),
                min_value=safe_float(stats.get('minv', 0))
            )
        
        # 解析财报影响（使用第一个指标的数据）
        impacts = []
        first_data = raw_data_dict[first_metric]
        for item in first_data.get('priceMetricsInfluencesList', []):
            metrics_data = item.get('metrics', {}).get('mcw', {}).get('q', {}).get('bs', {}).get('tetoshopc', {})
            if metrics_data:
                impacts.append(ReportImpact(
                    date=item.get('date', '')[:10],
                    report_date=item.get('reportDate', '')[:10],
                    report_type=item.get('reportType', ''),
                    influence_date=item.get('influenceDate', '')[:10],
                    metrics_name=item.get('metricsName', ''),
                    total_equity=safe_float(metrics_data.get('t_o', 0)) / 1e8,
                    yoy_change=safe_float(metrics_data.get('t_y2y', 0))
                ))
        
        # 解析财务指标
        financials = []
        for item in first_data.get('fsMetricsList', []):
            financials.append(FinancialMetrics(
                date=item.get('date', '')[:10],
                report_date=item.get('reportDate', '')[:10],
                report_type=item.get('reportType', ''),
                standard_date=item.get('standardDate', '')[:10]
            ))
        
        return ComprehensiveData(
            stock_info=None,
            daily_data=daily_data,
            pe_stats=create_stats('pe_ttm'),
            pb_stats=create_stats('pb'),
            ps_stats=create_stats('ps_ttm'),
            dyr_stats=create_stats('dyr'),
            report_impacts=impacts,
            financial_metrics=financials
        )
    
    def get_comprehensive_data(self, code: str, granularity: str = None, save_to_db: bool = None,
                               smart_granularity: bool = True) -> Optional[ComprehensiveData]:
        """
        获取全面多指标数据（自动识别类型）
        
        Args:
            code: 股票代码
            granularity: 时间粒度 (y1/y3/y5/y10/y20/fs)，None时自动选择
            save_to_db: 是否保存到数据库，None时使用实例的auto_save设置
            smart_granularity: 是否智能选择粒度（已有数据时用y1增量更新）
            
        Returns:
            ComprehensiveData 对象或 None
        """
        # 获取基本信息
        info = self.get_stock_info(code)
        if not info:
            log_error(f"❌ 获取 {code} 基本信息失败")
            return None
        
        print(f"✅ 获取到 {info.name} ({code}) 基本信息")
        
        stock_type = self._get_stock_type(code)
        
        # 智能选择粒度
        if granularity is None:
            if smart_granularity and self.db and self.db.has_stock_data(info.stock_id):
                summary = self.db.get_data_summary(info.stock_id)
                print(f"📊 数据库已有 {summary['total_records']} 条数据 ({summary['min_date']} ~ {summary['max_date']})")
                granularity = 'y1'
                print(f"💡 智能选择粒度: y1 (增量更新)")
            else:
                granularity = 'fs'
                print(f"💡 默认粒度: fs (全部数据)")
        
        if stock_type == 'company':
            # 公司：一次性请求所有指标
            log_info(f"🔄 获取公司全面数据 (粒度: {granularity})...")
            raw_data = self._fetch_company_metrics(info.stock_id, granularity)
            if not raw_data:
                log_error("❌ 获取公司数据失败")
                return None
            
            result = self._parse_company_data(raw_data)
            result.stock_info = self._enrich_stock_info_from_latest_daily(
                info, result.daily_data
            )

        else:
            # 指数：分批请求
            log_info(f"🔄 获取指数全面数据 (粒度: {granularity})...")
            raw_data_dict = self._fetch_index_all_metrics(info.stock_id, granularity)
            if not raw_data_dict:
                log_error("❌ 获取指数数据失败")
                return None
            
            result = self._parse_index_data(raw_data_dict)
            result.stock_info = self._enrich_stock_info_from_latest_daily(
                info, result.daily_data
            )

        print(f"✅ 成功获取 {len(result.daily_data)} 条历史数据")

        # 判断是否保存到数据库
        should_save = save_to_db if save_to_db is not None else self.auto_save
        if should_save and self.db:
            self.save_to_database(result, granularity, stock_type)
        
        return result
    
    def save_to_database(self, data: ComprehensiveData, granularity: str = 'fs', 
                         stock_type: str = 'company') -> dict:
        """
        将数据保存到数据库
        
        Args:
            data: ComprehensiveData 对象
            granularity: 时间粒度
            stock_type: 股票类型 (company/index)
            
        Returns:
            保存结果统计
        """
        if not self.db:
            log_error("❌ 数据库未初始化")
            return {}
        
        print(f"💾 正在保存数据到数据库...")
        result = self.db.save_comprehensive_data(data, granularity, stock_type)
        
        print(f"✅ 数据保存完成:")
        print(f"   - 基本信息: {'成功' if result.get('stock_info') else '失败'}")
        print(f"   - 每日数据: {result.get('daily_count', 0)} 条")
        print(f"   - 统计指标: {result.get('stats_saved', 0)} 个")
        print(f"   - 财报影响: {result.get('impact_count', 0)} 条")
        
        return result
    
    def export_json(self, data: ComprehensiveData, filepath: str):
        """导出数据到JSON"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data.to_dict(), f, ensure_ascii=False, indent=2)
        print(f"✅ 数据已导出到: {filepath}")
    
    def screen_undervalued_stocks(
        self,
        area_code: str = "cn",
        pe_percentile_max: float = 0.20,
        pb_percentile_max: float = 0.20,
        ps_percentile_max: float = 0.20,
        dyr_percentile_min: float = 0.80,
        page_size: int = 200,
        page_index: int = 0
    ) -> Optional[UndervaluedScreenerResult]:
        """
        筛选低估股票池
        
        通过估值指标历史分位筛选低估股票：
        - PE-TTM 历史分位 < pe_percentile_max（默认20%）
        - PB 历史分位 < pb_percentile_max（默认20%）
        - PS-TTM 历史分位 < ps_percentile_max（默认20%）
        - 股息率历史分位 > dyr_percentile_min（默认80%）
        
        Args:
            area_code: 地区代码，"cn"为A股，"hk"为港股
            pe_percentile_max: PE历史分位上限（0-1）
            pb_percentile_max: PB历史分位上限（0-1）
            ps_percentile_max: PS历史分位上限（0-1）
            dyr_percentile_min: 股息率历史分位下限（0-1）
            page_size: 每页返回数量
            page_index: 页码，从0开始
            
        Returns:
            UndervaluedScreenerResult 对象或 None
        """
        # A股和港股的字段名略有不同
        if area_code == "cn":
            body = {
                "areaCode": "cn",
                "ranges": {
                    "market": "a",
                    "stockBourseTypes": ["sh", "sz_gem", "sh_sti", "sz_mb", "sh_mb", "bj", "sz"],
                    "mutualMarkets": {"selectedMutualMarkets": [], "selectType": "include"},
                    "multiMarketListedType": {"selectedMultiMarketListedTypes": [], "selectType": "include"},
                    "excludeBlacklist": False,
                    "excludeDelisted": False,
                    "excludeBourseType": False,
                    "excludeSpecialTreatment": False,
                    "constituentsPerspectiveType": "history",
                    "specialTreatmentOnly": False
                },
                "filterList": [
                    {"id": "pm.pb_wo_gw.y10.cvpos", "min": 0, "max": pb_percentile_max, "value": "all", "date": "latest"},
                    {"id": "pm.d_pe_ttm.y10.cvpos", "min": 0, "max": pe_percentile_max, "value": "all", "date": "latest"},
                    {"id": "pm.ps_ttm.y10.cvpos", "min": 0, "max": ps_percentile_max, "value": "all", "date": "latest"},
                    {"id": "pm.dyr.y10.cvpos", "min": dyr_percentile_min, "max": 1, "value": "all", "date": "latest"}
                ],
                "customFilterList": [],
                "industrySource": "sw_2021",
                "industryLevel": "three",
                "sortName": "pm.latest.pb_wo_gw.y10.cvpos",
                "sortOrder": "desc",
                "pageIndex": page_index,
                "pageSize": page_size
            }
        else:  # hk
            body = {
                "areaCode": "hk",
                "ranges": {
                    "stockBourseTypes": [],
                    "mutualMarkets": {"selectedMutualMarkets": [], "selectType": "include"},
                    "multiMarketListedType": {"selectedMultiMarketListedTypes": [], "selectType": "include"},
                    "excludeBlacklist": False,
                    "excludeDelisted": False,
                    "excludeBourseType": False,
                    "constituentsPerspectiveType": "history"
                },
                "filterList": [
                    {"id": "pm.pe_ttm.y10.cvpos", "min": 0, "max": pe_percentile_max, "value": "all", "date": "latest"},
                    {"id": "pm.ps_ttm.y10.cvpos", "min": 0, "max": ps_percentile_max, "value": "all", "date": "latest"},
                    {"id": "pm.pb.y10.cvpos", "min": 0, "max": pb_percentile_max, "value": "all", "date": "latest"},
                    {"id": "pm.dyr.y10.cvpos", "min": dyr_percentile_min, "max": 1, "value": "all", "date": "latest"}
                ],
                "customFilterList": [],
                "industrySource": "hsi",
                "industryLevel": "three",
                "sortName": "pm.latest.pe_ttm.y10.cvpos",
                "sortOrder": "desc",
                "pageIndex": page_index,
                "pageSize": page_size
            }
        
        url = "https://www.lixinger.com/api/company/screener"
        log_info(f"🔄 正在筛选{'A股' if area_code == 'cn' else '港股'}低估股票...")
        
        data = self._request(url, method='POST', body=body)
        if not data:
            log_error("❌ 筛选请求失败")
            return None
        
        total = data.get('total', 0)
        rows = data.get('rows', [])
        
        stocks = []
        for row in rows:
            stock = row.get('stock', {})
            metrics_data = row.get('data', {}).get('pm', {}).get('latest', {})
            industry = stock.get('industry', {})
            
            # 根据市场解析字段名
            if area_code == "cn":
                pb_key = "pb_wo_gw.y10.cvpos"
                pe_key = "d_pe_ttm.y10.cvpos"
            else:
                pb_key = "pb.y10.cvpos"
                pe_key = "pe_ttm.y10.cvpos"
            
            screener_stock = ScreenerStock(
                stock_id=str(stock.get('_id', '')),
                name=stock.get('name', ''),
                code=stock.get('stockCode', ''),
                exchange=stock.get('exchange', ''),
                market=stock.get('market', ''),
                area_code=stock.get('areaCode', area_code),
                industry_name=industry.get('name', ''),
                industry_level=industry.get('level', ''),
                ipo_date=stock.get('ipoDate', '')[:10] if stock.get('ipoDate') else '',
                pb_percentile=metrics_data.get(pb_key, 0),
                pe_percentile=metrics_data.get(pe_key, 0),
                ps_percentile=metrics_data.get('ps_ttm.y10.cvpos', 0),
                dyr_percentile=metrics_data.get('dyr.y10.cvpos', 0)
            )
            stocks.append(screener_stock)
        
        print(f"✅ 筛选完成，共 {total} 条结果，当前页 {len(stocks)} 条")
        
        return UndervaluedScreenerResult(
            total=total,
            stocks=stocks,
            area_code=area_code,
            filter_params={
                'pe_percentile_max': pe_percentile_max,
                'pb_percentile_max': pb_percentile_max,
                'ps_percentile_max': ps_percentile_max,
                'dyr_percentile_min': dyr_percentile_min
            }
        )


if __name__ == '__main__':
    spider = LixingerSpider()
    
    # 测试公司
    print("="*60)
    print("测试公司: 600519 贵州茅台")
    print("="*60)
    data = spider.get_comprehensive_data('600519', 'fs')
    if data:
        print(f"\n{data.stock_info.name}")
        print(f"PE-TTM: {data.stock_info.pe_ttm:.2f}, PB: {data.stock_info.pb:.2f}, PS: {data.stock_info.ps_ttm:.2f}")
        print(f"历史数据: {len(data.daily_data)} 条")
        print(f"财报影响: {len(data.report_impacts)} 条")
        spider.export_json(data, 'company_600519.json')
    
    # 测试指数
    print("\n" + "="*60)
    print("测试指数: 980092 自由现金流")
    print("="*60)
    data2 = spider.get_comprehensive_data('980092', 'fs')
    if data2:
        print(f"\n{data2.stock_info.name}")
        print(f"PE-TTM: {data2.stock_info.pe_ttm:.2f}, PB: {data2.stock_info.pb:.2f}")
        print(f"历史数据: {len(data2.daily_data)} 条")
        spider.export_json(data2, 'index_980092.json')
