#!/usr/bin/env python3
"""
MXSearchProvider - 妙想金融搜索Provider
P0级别 - 金融资讯搜索主源
配额由服务端按日控制，客户端不设秒级间隔。

提供统一的search()接口，支持:
- search_news() - 新闻搜索
- search_report() - 研报搜索
- search_announcement() - 公告搜索
"""

import os
import sys
import time
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path
from enum import Enum

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from teakfds.datasource_log import log_external_request

from teakfds.providers.base_provider import BaseProvider, ProviderCapabilities
from teakfds.models import ProviderStatus


class SearchType(Enum):
    """搜索类型"""
    NEWS = "news"           # 新闻
    REPORT = "report"       # 研报
    ANNOUNCEMENT = "announcement"  # 公告
    ALL = "all"             # 全部


class MXSearchProvider(BaseProvider):
    """
    妙想金融搜索Provider
    P0级别搜索主源，支持新闻、研报、公告搜索
    
    配额由妙想侧按日限制；客户端不做秒级请求间隔。
    """
    
    name = "mx_search"
    display_name = "妙想搜索"
    priority = 100
    
    capabilities = ProviderCapabilities(
        supports_news=True,
        markets=['a_share', 'hk', 'us']
    )
    
    BASE_URL = "https://mkapi2.dfcfs.com/finskillshub/api/claw/news-search"

    API_KEY_PATHS = [
        Path.home() / 'agents_documents' / 'MX_APIKEY.txt',
        Path.home() / '.openclaw' / 'credentials' / 'MX_APIKEY.txt',
    ]

    def __init__(self, api_key: Optional[str] = None):
        super().__init__()
        self.api_key = api_key or self._load_api_key()
        self._last_quota_limited = False

    @staticmethod
    def _message_indicates_quota(msg: str) -> bool:
        if not msg:
            return False
        keys = ('限流', '次数', '额度', '配额', '用完', 'quota', 'rate limit')
        m = msg.lower()
        return any(k.lower() in m for k in keys)

    def last_quota_limited(self) -> bool:
        return getattr(self, '_last_quota_limited', False)

    def _load_api_key(self) -> str:
        """仅 ``MX_APIKEY`` 环境变量或文件（与 mx-data 共用配额）。"""
        api_key = os.getenv("MX_APIKEY")
        if api_key:
            return api_key.strip()

        for path in self.API_KEY_PATHS:
            if path.exists():
                try:
                    content = path.read_text().strip()
                    if content:
                        return content
                except Exception:
                    continue

        return ""

    def _make_request(self, query: str) -> Optional[Dict[str, Any]]:
        """发送搜索请求"""
        self._last_quota_limited = False

        headers = {
            "Content-Type": "application/json",
            "apikey": self.api_key
        }
        data = {"query": query}
        
        t0 = time.perf_counter()
        try:
            import requests
            response = requests.post(self.BASE_URL, headers=headers, json=data, timeout=30)
            elapsed = (time.perf_counter() - t0) * 1000
            log_external_request(
                provider="mx_search",
                method="POST",
                url=str(response.url),
                action="news_search",
                success=response.status_code == 200,
                status_code=response.status_code,
                duration_ms=elapsed,
                message=(query[:500] if query else ""),
                params={"query": (query[:4000] if query else "")},
                caller="MXSearchProvider._make_request",
            )
            response.raise_for_status()
            result = response.json()

            if result.get("status") == 0:
                return result
            msg = str(
                result.get("message")
                or result.get("msg")
                or result.get("info")
                or result
            )
            if self._message_indicates_quota(msg):
                self._last_quota_limited = True
            return None
        except Exception as e:
            log_external_request(
                provider="mx_search",
                method="POST",
                url=self.BASE_URL,
                action="news_search",
                success=False,
                duration_ms=(time.perf_counter() - t0) * 1000,
                message=f"{e!s}; query={query[:300]!r}",
                params={"query": (query[:4000] if query else "")},
                caller="MXSearchProvider._make_request",
            )
            print(f"MXSearchProvider request error: {e}")
            return None
    
    def is_available(self) -> bool:
        """已配置 API Key 即视为可用（避免探测消耗配额）。"""
        return bool(self.api_key and str(self.api_key).strip())
    
    def get_status(self) -> ProviderStatus:
        """获取Provider状态"""
        available = self.is_available()
        return ProviderStatus(
            name=self.name,
            available=available,
            last_success=datetime.now().isoformat() if available else None
        )
    
    def search(self, query: str, search_type: SearchType = SearchType.ALL) -> List[Dict[str, Any]]:
        """
        统一搜索接口
        
        Args:
            query: 搜索关键词
            search_type: 搜索类型
        
        Returns:
            搜索结果列表
        """
        # 根据搜索类型优化查询
        if search_type == SearchType.NEWS:
            enhanced_query = f"{query} 新闻"
        elif search_type == SearchType.REPORT:
            enhanced_query = f"{query} 研报"
        elif search_type == SearchType.ANNOUNCEMENT:
            enhanced_query = f"{query} 公告"
        else:
            enhanced_query = query
        
        result = self._make_request(enhanced_query)
        if not result:
            return []
        
        return self._parse_search_result(result, search_type)
    
    def _parse_search_result(self, result: Dict[str, Any], search_type: SearchType) -> List[Dict[str, Any]]:
        """解析搜索结果"""
        try:
            data = result.get("data", {}).get("data", {})
            search_response = data.get("llmSearchResponse", {})
            items = search_response.get("data", [])
            
            if not items:
                return []
            
            # 按类型过滤
            filtered_items = []
            for item in items:
                info_type = item.get("informationType", "").upper()
                
                # 类型映射
                type_map = {
                    "NEWS": "news",
                    "REPORT": "report",
                    "ANNOUNCEMENT": "announcement"
                }
                
                mapped_type = type_map.get(info_type, "other")
                
                # 根据搜索类型过滤
                if search_type == SearchType.ALL:
                    filtered_items.append(self._format_item(item, mapped_type))
                elif search_type.value == mapped_type:
                    filtered_items.append(self._format_item(item, mapped_type))
            
            return filtered_items
            
        except Exception as e:
            print(f"MXSearchProvider parse error: {e}")
            return []
    
    def _format_item(self, item: Dict, info_type: str) -> Dict[str, Any]:
        """格式化单个搜索结果"""
        return {
            "title": item.get("title", ""),
            "content": item.get("content", ""),
            "date": item.get("date", ""),
            "type": info_type,
            "source": item.get("insName", ""),
            "entity": item.get("entityFullName", ""),
            "rating": item.get("rating", ""),
            "url": item.get("url", "")
        }
    
    def search_news(self, query: str, days: int = 7) -> List[Dict[str, Any]]:
        """
        搜索新闻
        
        Args:
            query: 搜索关键词（股票代码或公司名称）
            days: 多少天内的新闻
        
        Returns:
            新闻列表
        """
        # 构建时间范围查询
        time_filter = ""
        if days <= 1:
            time_filter = "今日"
        elif days <= 7:
            time_filter = "最近一周"
        elif days <= 30:
            time_filter = "最近一个月"
        
        search_query = f"{query} {time_filter}新闻" if time_filter else f"{query} 新闻"
        
        result = self._make_request(search_query)
        if not result:
            return []
        
        return self._parse_search_result(result, SearchType.NEWS)
    
    def search_report(self, query: str, count: int = 10) -> List[Dict[str, Any]]:
        """
        搜索研报
        
        Args:
            query: 搜索关键词（股票代码或公司名称）
            count: 最多返回条数
        
        Returns:
            研报列表
        """
        search_query = f"{query} 研报"
        
        result = self._make_request(search_query)
        if not result:
            return []
        
        rows = self._parse_search_result(result, SearchType.REPORT)
        if count and len(rows) > count:
            return rows[:count]
        return rows
    
    def search_announcement(self, query: str, days: int = 30) -> List[Dict[str, Any]]:
        """
        搜索公告
        
        Args:
            query: 搜索关键词（股票代码或公司名称）
            days: 多少天内的公告
        
        Returns:
            公告列表
        """
        # 构建时间范围查询
        time_filter = ""
        if days <= 1:
            time_filter = "今日"
        elif days <= 7:
            time_filter = "最近一周"
        elif days <= 30:
            time_filter = "最近一个月"
        
        search_query = f"{query} {time_filter}公告" if time_filter else f"{query} 公告"
        
        result = self._make_request(search_query)
        if not result:
            return []
        
        return self._parse_search_result(result, SearchType.ANNOUNCEMENT)
    
    def news(self, symbol: str = None, days: int = 7) -> List[Dict]:
        """
        获取新闻 (BaseProvider接口实现)
        
        Args:
            symbol: 股票代码
            days: 多少天内的新闻
        
        Returns:
            新闻列表
        """
        if not symbol:
            # 如果没有指定代码，搜索市场热点
            return self.search_news("A股热点", days)
        
        return self.search_news(symbol, days)
    
    def format_results(self, results: List[Dict[str, Any]]) -> str:
        """
        格式化搜索结果为可读文本
        
        Args:
            results: 搜索结果列表
        
        Returns:
            格式化文本
        """
        if not results:
            return "未找到相关资讯"
        
        output = []
        output.append(f"搜索结果: 共找到 {len(results)} 条相关资讯\n")
        
        for i, item in enumerate(results, 1):
            title = item.get("title", "无标题")
            content = item.get("content", "无内容")
            date = item.get("date", "")
            source = item.get("source", "")
            info_type = item.get("type", "")
            entity = item.get("entity", "")
            rating = item.get("rating", "")
            
            # 类型中文映射
            type_map = {
                "news": "新闻",
                "report": "研报",
                "announcement": "公告"
            }
            type_cn = type_map.get(info_type, info_type)
            
            output.append(f"--- {i}. {title} ---")
            
            meta = []
            if entity:
                meta.append(f"证券: {entity}")
            if source:
                meta.append(f"来源: {source}")
            if date:
                # 只取日期部分
                date_part = date.split()[0] if ' ' in date else date
                meta.append(f"日期: {date_part}")
            if type_cn:
                meta.append(f"类型: {type_cn}")
            if rating:
                meta.append(f"评级: {rating}")
            
            if meta:
                output.append(" | ".join(meta))
            
            if content:
                output.append("")
                # 限制内容长度
                content_preview = content[:300] + "..." if len(content) > 300 else content
                output.append(content_preview)
            
            output.append("")
        
        return "\n".join(output)


# 全局实例
_mx_search_provider: Optional[MXSearchProvider] = None


def get_mx_search_provider() -> MXSearchProvider:
    """获取MXSearchProvider全局实例"""
    global _mx_search_provider
    if _mx_search_provider is None:
        _mx_search_provider = MXSearchProvider()
    return _mx_search_provider


if __name__ == '__main__':
    print("Testing MXSearchProvider...")
    provider = MXSearchProvider()
    
    print(f"\nAvailable: {provider.is_available()}")
    
    # 测试搜索新闻
    print("\n测试新闻搜索:")
    news = provider.search_news("贵州茅台", days=7)
    if news:
        print(f"  找到 {len(news)} 条新闻")
        for item in news[:3]:
            print(f"  - {item.get('title', '')}")
    
    # 测试搜索研报
    print("\n测试研报搜索:")
    reports = provider.search_report("贵州茅台")
    if reports:
        print(f"  找到 {len(reports)} 条研报")
        for item in reports[:3]:
            print(f"  - {item.get('title', '')}")
    
    # 测试搜索公告
    print("\n测试公告搜索:")
    announcements = provider.search_announcement("贵州茅台", days=30)
    if announcements:
        print(f"  找到 {len(announcements)} 条公告")
        for item in announcements[:3]:
            print(f"  - {item.get('title', '')}")
    
    print("\n✓ MXSearchProvider test completed!")
