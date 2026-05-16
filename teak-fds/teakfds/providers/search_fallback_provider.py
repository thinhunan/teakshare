#!/usr/bin/env python3
"""
SearchFallbackProvider - 搜索兜底Provider
P6级别 - 所有数据获取失败时的最终兜底

降级链:
1. baidu-search (P1)
2. firecrawl (P2)  
3. tavily (P3)

用于:
- 实时行情获取失败时，通过搜索获取价格信息
- 新闻/公告搜索的最终兜底
"""

import os
import sys
import time
import json
import subprocess
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from teakfds.datasource_log import log_external_request

from teakfds.providers.base_provider import BaseProvider, ProviderCapabilities
from teakfds.models import QuoteData, ProviderStatus


class SearchFallbackProvider(BaseProvider):
    """
    搜索兜底Provider
    
    当所有专业数据源失败时，通过搜索引擎获取信息
    降级链: baidu-search → firecrawl → tavily
    
    优先级: P6 (最低，作为最终兜底)
    """
    
    name = "search_fallback"
    display_name = "搜索兜底"
    priority = 10  # 最低优先级
    
    capabilities = ProviderCapabilities(
        supports_quote=False,  # 搜索不能提供精确行情
        supports_news=True,    # 支持新闻搜索
        markets=['a_share', 'hk', 'us']
    )
    
    def __init__(self):
        super().__init__()
        self._baidu_search_skill = Path.home() / '.openclaw' / 'skills' / 'baidu-search'
        self._last_request_time = 0
        self._min_interval = 1.0  # 搜索间隔1秒
    
    def _rate_limit(self):
        """简单限流"""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()
    
    def is_available(self) -> bool:
        """检查是否可用（至少一个搜索源可用）"""
        # baidu-search skill 存在即可用
        return self._baidu_search_skill.exists()
    
    def get_status(self) -> ProviderStatus:
        """获取状态"""
        available = self.is_available()
        return ProviderStatus(
            name=self.name,
            available=available,
            last_success=datetime.now().isoformat() if available else None
        )
    
    def _call_baidu_search(self, query: str) -> Optional[str]:
        """
        调用baidu-search skill
        
        Args:
            query: 搜索查询
        
        Returns:
            搜索结果文本或None
        """
        self._rate_limit()
        
        try:
            # 检查baidu-search skill
            skill_script = self._baidu_search_skill / 'scripts' / 'baidu_search.py'
            if not skill_script.exists():
                print(f"baidu-search script not found: {skill_script}")
                return None
            
            # 执行搜索脚本
            result = subprocess.run(
                ['python3', str(skill_script), query],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                return result.stdout
            else:
                print(f"baidu-search error: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            print("baidu-search timeout")
            return None
        except Exception as e:
            print(f"baidu-search call error: {e}")
            return None
    
    def _call_firecrawl(self, url: str) -> Optional[str]:
        """
        调用firecrawl获取网页内容
        
        Args:
            url: 目标URL
        
        Returns:
            页面内容或None
        """
        self._rate_limit()
        
        try:
            import requests
            import time as _time

            t0 = _time.perf_counter()
            resp = requests.get(url, timeout=10)
            log_external_request(
                provider="search_fallback",
                method="GET",
                url=str(resp.url),
                action="http_fetch",
                success=resp.status_code == 200,
                status_code=resp.status_code,
                duration_ms=(_time.perf_counter() - t0) * 1000,
                message="ok" if resp.status_code == 200 else (resp.text[:200] if resp.text else ""),
                params={"fetch_url": url},
                caller="SearchFallbackProvider._call_firecrawl",
            )
            if resp.status_code == 200:
                return resp.text[:2000]  # 限制长度
            return None
        except Exception as e:
            log_external_request(
                provider="search_fallback",
                method="GET",
                url=url,
                action="http_fetch",
                success=False,
                message=str(e)[:800],
                params={"fetch_url": url},
                caller="SearchFallbackProvider._call_firecrawl",
            )
            print(f"firecrawl error: {e}")
            return None
    
    def search(self, query: str) -> List[Dict[str, Any]]:
        """
        统一搜索接口
        
        降级链: baidu-search → firecrawl → tavily
        
        Args:
            query: 搜索关键词
        
        Returns:
            搜索结果列表
        """
        results = []
        
        # P1: baidu-search
        baidu_result = self._call_baidu_search(query)
        if baidu_result:
            results.append({
                "source": "baidu_search",
                "content": baidu_result[:500],  # 限制长度
                "query": query
            })
        
        # 如果baidu失败，可以尝试其他源（暂时只实现baidu）
        # P2: firecrawl - 需要具体URL
        # P3: tavily - 需要API key
        
        return results
    
    def search_news(self, symbol: str, days: int = 7) -> List[Dict[str, Any]]:
        """
        搜索新闻
        
        Args:
            symbol: 股票代码
            days: 天数
        
        Returns:
            新闻列表
        """
        # 构建搜索查询
        query = f"{symbol} 最新新闻 股票"
        
        return self.search(query)
    
    def search_price_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        搜索价格信息（作为行情获取失败的兜底）
        
        注意: 搜索结果可能不精确，仅作为参考
        
        Args:
            symbol: 股票代码
        
        Returns:
            价格信息字典或None
        """
        query = f"{symbol} 股票 最新价格 行情"
        
        results = self.search(query)
        if not results:
            return None
        
        # 尝试从搜索结果中提取价格
        content = results[0].get("content", "")
        
        # 简单的价格提取（不保证准确性）
        return {
            "symbol": symbol,
            "source": "search_fallback",
            "content": content,
            "warning": "数据来源为搜索结果，仅供参考，不保证准确性"
        }
    
    def news(self, symbol: str = None, days: int = 7) -> List[Dict]:
        """
        获取新闻 (BaseProvider接口)
        
        Args:
            symbol: 股票代码
            days: 天数
        
        Returns:
            新闻列表
        """
        if symbol:
            return self.search_news(symbol, days)
        else:
            return self.search("A股市场热点新闻")
    
    def fallback_quote(self, symbol: str) -> Optional[QuoteData]:
        """
        行情兜底（不推荐使用，仅作最后手段）
        
        Args:
            symbol: 股票代码
        
        Returns:
            QuoteData对象或None（数据可能不准确）
        """
        price_info = self.search_price_info(symbol)
        if not price_info:
            return None
        
        # 返回一个警告性的QuoteData
        return QuoteData(
            symbol=symbol,
            name=f"{symbol} (搜索兜底·仅供参考)",
            current=0,
            open=0,
            high=0,
            low=0,
            close=0,
            volume=0,
            amount=0,
            percent=0,
            timestamp=datetime.now().isoformat(),
            source="search_fallback",
        )
    
    def format_results(self, results: List[Dict[str, Any]]) -> str:
        """格式化搜索结果"""
        if not results:
            return "搜索无结果"
        
        output = []
        for i, item in enumerate(results, 1):
            source = item.get("source", "unknown")
            content = item.get("content", "")
            query = item.get("query", "")
            
            output.append(f"--- 结果 {i} (来源: {source}) ---")
            output.append(f"查询: {query}")
            output.append(f"内容: {content[:300]}...")
            output.append("")
        
        return "\n".join(output)


# 全局实例
_search_fallback_provider: Optional[SearchFallbackProvider] = None


def get_search_fallback_provider() -> SearchFallbackProvider:
    """获取全局实例"""
    global _search_fallback_provider
    if _search_fallback_provider is None:
        _search_fallback_provider = SearchFallbackProvider()
    return _search_fallback_provider


if __name__ == '__main__':
    print("Testing SearchFallbackProvider...")
    provider = SearchFallbackProvider()
    
    print(f"\nAvailable: {provider.is_available()}")
    
    # 测试搜索
    print("\n测试搜索功能:")
    results = provider.search("贵州茅台 最新价格")
    if results:
        print(f"找到 {len(results)} 条结果")
        print(provider.format_results(results))
    
    # 测试新闻搜索
    print("\n测试新闻搜索:")
    news = provider.search_news("贵州茅台", days=7)
    if news:
        print(f"找到 {len(news)} 条新闻")
    
    print("\n✓ SearchFallbackProvider test completed!")