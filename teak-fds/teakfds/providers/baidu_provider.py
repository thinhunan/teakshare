#!/usr/bin/env python3
"""
BaiduProvider - 百度股市通数据源

提供:
- 概念板块归属 (行业/概念/地域三维分类)
- 个股资金流向 (分钟级实时 + 日级历史)

零鉴权，免费无 key，不封 IP。
"""

from typing import Optional, Dict, Any, List
from datetime import datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from teakfds.datasource_log import log_info, log_warn, log_error
from teakfds.providers.base_provider import BaseProvider, ProviderCapabilities
from teakfds.models import ProviderStatus


_BAIDU_PAE_HEADERS = {
    "Host": "finance.pae.baidu.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/117.0.0.0",
    "Accept": "application/vnd.finance-web.v1+json",
    "Origin": "https://gushitong.baidu.com",
    "Referer": "https://gushitong.baidu.com/",
}


def _strip_prefix(symbol: str) -> str:
    """SH600519 / SZ000001 → 600519 / 000001"""
    s = symbol.upper()
    for pfx in ("SH", "SZ", "BJ"):
        if s.startswith(pfx):
            return s[len(pfx):]
    if "." in s:
        return s.split(".")[0]
    return symbol


class BaiduProvider(BaseProvider):
    name = "baidu"
    display_name = "百度股市通"
    priority = 15

    capabilities = ProviderCapabilities(
        supports_money_flow=True,
        markets=["a_share"],
    )

    def is_available(self) -> bool:
        return True

    def get_status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            available=True,
            last_success=datetime.now().isoformat(),
        )

    # ========== 概念板块归属 ==========

    def concept_blocks(self, symbol: str) -> Optional[Dict[str, Any]]:
        """个股所属行业/概念/地域板块。

        Returns:
            {industry: [...], concept: [...], region: [...], concept_tags: [str, ...]}
        """
        import requests

        code = _strip_prefix(symbol)
        url = (
            f"https://finance.pae.baidu.com/api/getrelatedblock"
            f"?code={code}&market=ab&typeCode=all&finClientType=pc"
        )
        try:
            r = requests.get(url, headers=_BAIDU_PAE_HEADERS, timeout=10)
            d = r.json()
        except Exception as e:
            log_error(f"baidu concept_blocks error: {e}")
            return None

        if str(d.get("ResultCode", -1)) != "0":
            log_warn(f"baidu concept_blocks ResultCode={d.get('ResultCode')}")
            return None

        result: Dict[str, Any] = {"industry": [], "concept": [], "region": [], "concept_tags": []}
        for block in d.get("Result", []):
            block_type = block.get("type", "")
            for item in block.get("list", []):
                entry = {
                    "name": item.get("name", ""),
                    "change_pct": item.get("increase", ""),
                    "desc": item.get("desc", ""),
                }
                if "行业" in block_type:
                    result["industry"].append(entry)
                elif "概念" in block_type:
                    result["concept"].append(entry)
                    result["concept_tags"].append(entry["name"])
                elif "地域" in block_type:
                    result["region"].append(entry)
        return result

    # ========== 个股资金流向 (分钟级) ==========

    def fund_flow_realtime(self, symbol: str, date: str) -> Optional[List[Dict]]:
        """分钟级资金流向。

        Args:
            symbol: FDS 格式代码
            date: YYYYMMDD 紧凑格式
        """
        import requests

        code = _strip_prefix(symbol)
        url = (
            f"https://finance.pae.baidu.com/vapi/v1/fundflow"
            f"?code={code}&market=ab&date={date}&finClientType=pc"
        )
        try:
            r = requests.get(url, headers=_BAIDU_PAE_HEADERS, timeout=10)
            d = r.json()
        except Exception as e:
            log_error(f"baidu fund_flow_realtime error: {e}")
            return None

        if str(d.get("ResultCode", -1)) != "0":
            return None

        raw = d.get("Result", {}).get("update_data", "")
        if not raw:
            return None

        rows = []
        for segment in raw.split(";"):
            parts = segment.split(",")
            if len(parts) >= 9:
                rows.append({
                    "time": parts[0],
                    "mainForce": float(parts[2]) if parts[2] else 0,
                    "retail": float(parts[3]) if parts[3] else 0,
                    "super": float(parts[4]) if parts[4] else 0,
                    "large": float(parts[5]) if parts[5] else 0,
                    "price": float(parts[8]) if parts[8] else 0,
                })
        return rows

    # ========== 个股资金流向 (日级历史) ==========

    def fund_flow_history(self, symbol: str, days: int = 20) -> Optional[List[Dict]]:
        """日级资金流向（最近 N 交易日）；东财为主，百度 fundsortlist 已失效。"""
        from teakfds.integrations.eastmoney_fund_flow import fetch_stock_fund_flow_em
        from teakfds.normalize_finance import normalize_money_flow_rows

        rows = fetch_stock_fund_flow_em(symbol, days=days)
        if rows:
            return normalize_money_flow_rows(rows, source="eastmoney", days=days)

        import requests

        code = _strip_prefix(symbol)
        url = (
            f"https://finance.pae.baidu.com/vapi/v1/fundsortlist"
            f"?code={code}&market=ab&pn=0&rn={days}&finClientType=pc"
        )
        try:
            r = requests.get(url, headers=_BAIDU_PAE_HEADERS, timeout=10)
            d = r.json()
        except Exception as e:
            log_error(f"baidu fund_flow_history error: {e}")
            return None

        if str(d.get("ResultCode", -1)) != "0":
            return None

        result = d.get("Result") or {}
        legacy: List[Dict] = []
        for item in result.get("list", []) or []:
            legacy.append({
                "date": item.get("showtime", ""),
                "close": item.get("closepx", ""),
                "change_pct": item.get("ratio", ""),
                "superNetIn": item.get("superNetIn", ""),
                "largeNetIn": item.get("largeNetIn", ""),
                "mediumNetIn": item.get("mediumNetIn", ""),
                "littleNetIn": item.get("littleNetIn", ""),
                "mainIn": item.get("extMainIn", ""),
            })
        return normalize_money_flow_rows(legacy, source=self.name, days=days) if legacy else None

    # ========== BaseProvider 标准接口适配 ==========

    def money_flow(self, symbol: str, days: int = 30) -> Optional[List[Dict]]:
        """适配 BaseProvider 的 money_flow 接口，走日级历史。"""
        return self.fund_flow_history(symbol, days=days)


# 单例
_instance: Optional[BaiduProvider] = None


def get_baidu_provider() -> BaiduProvider:
    global _instance
    if _instance is None:
        _instance = BaiduProvider()
    return _instance
