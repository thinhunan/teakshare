#!/usr/bin/env python3
"""
CninfoProvider - 巨潮资讯 Provider
Official CSRC disclosure platform - 最权威的A股公告数据源

无需认证即可查询公告列表; PDF下载无需认证。
"""

import time
import json
from typing import Optional, List, Dict, Any
from datetime import datetime

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from teakfds.datasource_log import log_external_request, log_error

from teakfds.providers.base_provider import BaseProvider, ProviderCapabilities
from teakfds.models import ProviderStatus, normalize_symbol


class CninfoProvider(BaseProvider):
    """
    巨潮资讯 Provider

    提供公告列表查询和PDF下载。
    巨潮是证监会指定的法定信息披露平台，数据最权威完整。
    """

    name = "cninfo"
    display_name = "巨潮资讯"
    priority = 80  # 公告数据最高优先级

    capabilities = ProviderCapabilities(
        supports_announcement=True,
        markets=['a_share'],
    )

    QUERY_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
    PDF_BASE_URL = "https://static.cninfo.com.cn/"

    # 公告类别中文 → 巨潮代码映射
    CATEGORY_CODES = {
        '年报': 'category_ndbg_szsh',
        '半年报': 'category_bndbg_szsh',
        '一季报': 'category_yjdbg_szsh',
        '三季报': 'category_sjdbg_szsh',
        '业绩预告': 'category_yjygjxz_szsh',
        '权益分派': 'category_qyfpxzcs_szsh',
        '董事会': 'category_dshgg_szsh',
        '监事会': 'category_jshgg_szsh',
        '股东大会': 'category_gddh_szsh',
        '日常经营': 'category_rcjy_szsh',
        '公司治理': 'category_gszl_szsh',
        '中介报告': 'category_zj_szsh',
        '首发': 'category_sf_szsh',
        '增发': 'category_zf_szsh',
        '股权激励': 'category_gqjl_szsh',
        '配股': 'category_pg_szsh',
        '解禁': 'category_jj_szsh',
        '公司债': 'category_gszq_szsh',
        '可转债': 'category_kzzq_szsh',
        '其他融资': 'category_qtrz_szsh',
        '股权变动': 'category_gqbd_szsh',
        '补充更正': 'category_bcgz_szsh',
        '澄清致歉': 'category_cqdq_szsh',
        '风险提示': 'category_fxts_szsh',
        '特别处理和退市': 'category_tbclts_szsh',
        '退市整理期': 'category_tszlq_szsh',
    }

    def __init__(self):
        super().__init__()
        self._session = None

    def is_available(self) -> bool:
        """巨潮无需认证，始终可用"""
        return True

    def get_status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            available=True,
            last_success=datetime.now().isoformat()
        )

    def _ensure_session(self):
        """创建或复用 requests Session，并初始化cookie"""
        if self._session is None:
            import requests
            self._session = requests.Session()
            self._session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'Referer': 'https://www.cninfo.com.cn/new/disclosure',
            })
            # 初始化 cookie (巨潮需要先访问页面获取 JSESSIONID)
            try:
                self._session.get('https://www.cninfo.com.cn/new/disclosure', timeout=10)
            except Exception:
                pass
        return self._session

    @staticmethod
    def _fds_to_orgid(symbol: str) -> str:
        """FDS symbol → 巨潮 orgId (简化版, 使用纯代码查询)

        巨潮查询需要 orgId，但也可以用 stock+code 查询。
        这里使用简单的代码查询方式。
        """
        s = symbol.upper().strip()
        if s.startswith(('SH', 'SZ', 'BJ')):
            return s[2:]
        if '.' in s:
            return s.split('.')[0]
        return s

    @staticmethod
    def _category_to_code(category: str) -> str:
        """中文类别 → 巨潮代码"""
        if not category:
            return ''
        return CninfoProvider.CATEGORY_CODES.get(category, '')

    def announcement_list(
        self,
        symbol: str,
        category: str = '',
        start_date: str = None,
        end_date: str = None,
        page: int = 1,
        page_size: int = 30,
    ) -> Optional[Dict]:
        """查询公告列表

        Args:
            symbol: 股票代码 (FDS format) 或公司名称
            category: 公告类别 (中文，如 '年报')
            start_date: YYYY-MM-DD
            end_date: YYYY-MM-DD
            page: 页码
            page_size: 每页条数 (max 100)
        Returns:
            {'total': int, 'announcements': [dict], 'has_more': bool}
        """
        try:
            session = self._ensure_session()

            # 巨潮API的stock字段需要orgId格式(如gssh0600519)
            # 为简化，使用searchkey按公司名称/代码搜索
            code = self._fds_to_orgid(symbol)
            search_key = code  # 用纯代码搜索

            # 如果是FDS格式(如SH600519), 尝试转为名称搜索会更准确
            # 但名称查询需要额外API, 这里先用代码

            # 构建查询参数
            data = {
                'pageNum': str(page),
                'pageSize': str(min(page_size, 100)),
                'column': 'szse',
                'tabName': 'fulltext',
                'plate': '',
                'stock': '',
                'searchkey': search_key,
                'secid': '',
                'category': self._category_to_code(category),
                'trade': '',
                'seDate': f"{start_date or ''}~{end_date or ''}",
                'sortName': '',
                'sortType': '',
                'isHLtitle': 'true',
            }

            t0 = time.perf_counter()
            resp = session.post(self.QUERY_URL, data=data, timeout=15)
            elapsed = (time.perf_counter() - t0) * 1000

            log_external_request(
                provider="cninfo", method="POST", url=self.QUERY_URL,
                action="announcement_list", success=resp.status_code == 200,
                status_code=resp.status_code, duration_ms=elapsed,
                params={"searchkey": search_key, "category": category},
                caller="CninfoProvider.announcement_list",
            )

            if resp.status_code != 200:
                return None

            result = resp.json()
            ann_data = result.get('announcements', []) or []

            announcements = []
            for item in ann_data:
                ann = {
                    'title': item.get('announcementTitle', '').replace('<em>', '').replace('</em>', ''),
                    'sec_name': item.get('secName', '').replace('<em>', '').replace('</em>', ''),
                    'sec_code': item.get('secCode', ''),
                    'adjunct_url': item.get('adjunctUrl', ''),
                    'adjunct_size': item.get('adjunctSize', 0),
                    'adjunct_type': item.get('adjunctType', ''),
                    'announcement_time': item.get('announcementTime', ''),
                    'announcement_id': item.get('announcementId', ''),
                    'category': item.get('announcementType', ''),
                    'org_id': item.get('orgId', ''),
                }
                # 转换时间戳
                if ann['announcement_time']:
                    try:
                        ts = int(ann['announcement_time'])
                        ann['announcement_time'] = datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d %H:%M:%S')
                    except (ValueError, TypeError, OSError):
                        pass

                announcements.append(ann)

            total = result.get('totalAnnouncement', 0) or 0
            has_more = (page * page_size) < total

            return {
                'total': total,
                'announcements': announcements,
                'has_more': has_more,
                'source': self.name,
            }

        except Exception as e:
            log_error(f"CninfoProvider.announcement_list error for {symbol}: {e}")
            return None

    def announcement_pdf_url(self, adjunct_url: str) -> str:
        """构造PDF下载URL

        Args:
            adjunct_url: 查询结果中的 adjunctUrl 字段
        Returns: Full PDF download URL
        """
        if not adjunct_url:
            return ''
        return f"{self.PDF_BASE_URL}{adjunct_url}"

    def announcement_full_text(self, adjunct_url: str) -> Optional[str]:
        """获取公告全文 (下载PDF + 提取文本)

        Args:
            adjunct_url: 查询结果中的 adjunctUrl 字段
        Returns: 提取的文本内容或None
        """
        if not adjunct_url:
            return None

        pdf_url = self.announcement_pdf_url(adjunct_url)

        try:
            # 下载PDF
            session = self._ensure_session()
            resp = session.get(pdf_url, timeout=30)
            if resp.status_code != 200:
                return None

            pdf_bytes = resp.content
            if not pdf_bytes:
                return None

            # 尝试使用 pdfplumber 提取文本
            try:
                import pdfplumber
                import io
                texts = []
                with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                    for page in pdf.pages:
                        text = page.extract_text()
                        if text:
                            texts.append(text)
                return '\n'.join(texts) if texts else None
            except ImportError:
                # pdfplumber 未安装, 尝试 PyPDF2
                try:
                    from PyPDF2 import PdfReader
                    import io
                    reader = PdfReader(io.BytesIO(pdf_bytes))
                    texts = []
                    for page in reader.pages:
                        text = page.extract_text()
                        if text:
                            texts.append(text)
                    return '\n'.join(texts) if texts else None
                except ImportError:
                    log_error("Neither pdfplumber nor PyPDF2 available for PDF text extraction")
                    return None

        except Exception as e:
            log_error(f"CninfoProvider.announcement_full_text error: {e}")
            return None


# 全局实例
_cninfo_provider: Optional[CninfoProvider] = None


def get_cninfo_provider() -> CninfoProvider:
    """获取全局 CninfoProvider"""
    global _cninfo_provider
    if _cninfo_provider is None:
        _cninfo_provider = CninfoProvider()
    return _cninfo_provider


if __name__ == '__main__':
    print("Testing CninfoProvider...")
    provider = CninfoProvider()
    print(f"Available: {provider.is_available()}")

    print("\n测试公告列表:")
    result = provider.announcement_list('SH600519', category='年报')
    if result:
        print(f"  总数: {result['total']}")
        for ann in result['announcements'][:3]:
            print(f"  - {ann['title']} ({ann.get('announcement_time', '')})")
            if ann.get('adjunct_url'):
                print(f"    PDF: {provider.announcement_pdf_url(ann['adjunct_url'])}")

    print("\n✓ CninfoProvider test completed!")
