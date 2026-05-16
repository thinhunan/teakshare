#!/usr/bin/env python3
"""
IwencaiProvider - 问财自然语言选股 Provider
免费、无需认证，支持自然语言语义查询

可选依赖: pywencai (pip install pywencai)
"""

import time
from typing import Optional, List, Dict, Any
from datetime import datetime

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from teakfds.datasource_log import log_info, log_warn, log_error, log_external_request

from teakfds.providers.base_provider import BaseProvider, ProviderCapabilities
from teakfds.models import ProviderStatus


# 尝试导入 pywencai
try:
    import pywencai
    _PYWENCAI_AVAILABLE = True
except ImportError:
    _PYWENCAI_AVAILABLE = False
    pywencai = None


class IwencaiProvider(BaseProvider):
    """
    问财自然语言选股 Provider

    支持自然语言语义查询，例如:
    - "连续3年ROE大于15%的股票"
    - "市盈率小于20且净利润增速大于30%"
    - "北向资金连续5日净流入的股票"
    """

    name = "iwencai"
    display_name = "问财选股"
    priority = 50

    capabilities = ProviderCapabilities(
        supports_iwencai=True,
        markets=['a_share'],
    )

    # 请求间隔
    MIN_INTERVAL = 1.0

    def __init__(self):
        super().__init__()
        self._available = _PYWENCAI_AVAILABLE
        self._last_request_time = 0

    def is_available(self) -> bool:
        return _PYWENCAI_AVAILABLE

    def get_status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            available=self.is_available(),
            last_success=datetime.now().isoformat() if self.is_available() else None
        )

    def _wait_rate_limit(self):
        """限流"""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self.MIN_INTERVAL:
            time.sleep(self.MIN_INTERVAL - elapsed)
        self._last_request_time = time.time()

    def query(self, question: str, **kwargs) -> Optional[List[Dict]]:
        """自然语言选股查询 (pywencai.get)

        Args:
            question: 自然语言查询 (如 "连续3年ROE大于15%的股票")
            **kwargs: 传递给 pywencai.get 的额外参数
                - query_type: 查询类型 (默认 'stock')
                - loop: 是否循环查询 (默认 True)

        Returns:
            list of dicts (stock screening results)
        """
        if not self.is_available():
            return None

        q = (question or '').strip()
        if not q:
            return None

        try:
            self._wait_rate_limit()

            t0 = time.perf_counter()
            df = pywencai.get(query=q, **kwargs)
            elapsed = (time.perf_counter() - t0) * 1000

            log_external_request(
                provider="iwencai", method="POST", url="pywencai.get",
                action="nl_query", success=True, duration_ms=elapsed,
                params={"query": q[:500]}, caller="IwencaiProvider.query",
            )

            if df is None:
                return None
            if hasattr(df, 'empty') and df.empty:
                return None

            # 转换 DataFrame 列名为安全字符串
            df.columns = [str(c) for c in df.columns]
            records = df.to_dict('records')
            return records if records else None

        except Exception as e:
            log_error(f"IwencaiProvider.query error: {e}")
            log_external_request(
                provider="iwencai", method="POST", url="pywencai.get",
                action="nl_query", success=False, duration_ms=0,
                message=str(e)[:500], params={"query": q[:500]},
                caller="IwencaiProvider.query",
            )
            return None


# 全局实例
_iwencai_provider: Optional[IwencaiProvider] = None


def get_iwencai_provider() -> IwencaiProvider:
    """获取全局 IwencaiProvider"""
    global _iwencai_provider
    if _iwencai_provider is None:
        _iwencai_provider = IwencaiProvider()
    return _iwencai_provider


if __name__ == '__main__':
    print("Testing IwencaiProvider...")
    provider = IwencaiProvider()
    print(f"Available: {provider.is_available()}")

    if provider.is_available():
        print("\n测试自然语言查询:")
        results = provider.query("连续3年ROE大于15%的股票")
        if results:
            print(f"  找到 {len(results)} 只股票")
            for r in results[:5]:
                print(f"  - {r.get('股票代码', '')} {r.get('股票简称', '')}")

    print("\n✓ IwencaiProvider test completed!")
