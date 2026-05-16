#!/usr/bin/env python3
"""
THSProvider - 同花顺直调数据源

提供:
- 当日强势股 + 题材归因 reason tags (零鉴权, ~73ms)
- 北向资金 沪深股通分钟级实时流向 (hsgtApi)

零鉴权，免费无 key，不封 IP。
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, date as _date

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from teakfds.datasource_log import log_info, log_warn, log_error
from teakfds.providers.base_provider import BaseProvider, ProviderCapabilities
from teakfds.models import ProviderStatus


_THS_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "Chrome/117.0.0.0 Safari/537.36"
)


class THSProvider(BaseProvider):
    name = "ths"
    display_name = "同花顺直调"
    priority = 12

    capabilities = ProviderCapabilities(
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

    # ========== 当日强势股 + 题材归因 ==========

    def hot_stocks(self, trade_date: str = None) -> Optional[List[Dict]]:
        """同花顺当日强势股归因。

        Args:
            trade_date: YYYY-MM-DD, None=今天

        Returns:
            [{code, name, reason, close, change_pct, turnover_pct, amount, volume, dde_net, market}, ...]
        """
        import requests

        if trade_date is None:
            trade_date = _date.today().strftime("%Y-%m-%d")

        url = (
            f"http://zx.10jqka.com.cn/event/api/getharden/"
            f"date/{trade_date}/orderby/date/orderway/desc/charset/GBK/"
        )
        headers = {"User-Agent": _THS_UA}

        try:
            r = requests.get(url, headers=headers, timeout=10)
            data = r.json()
        except Exception as e:
            log_error(f"ths hot_stocks error: {e}")
            return None

        if data.get("errocode", 0) != 0:
            log_warn(f"ths hot_stocks error: {data.get('errormsg', '')}")
            return None

        rows = data.get("data") or []
        result = []
        for row in rows:
            result.append({
                "code": row.get("code", ""),
                "name": row.get("name", ""),
                "reason": row.get("reason", ""),
                "close": row.get("close"),
                "change_pct": row.get("zhangfu"),
                "turnover_pct": row.get("huanshou"),
                "amount": row.get("chengjiaoe"),
                "volume": row.get("chengjiaoliang"),
                "dde_net": row.get("ddejingliang"),
                "market": row.get("market"),
            })
        return result

    # ========== 北向资金实时分钟流向 ==========

    def north_money_realtime(self) -> Optional[List[Dict]]:
        """沪深股通当日实时分钟流向。

        Returns:
            [{time, hgt_yi, sgt_yi}, ...] 单位亿元
        """
        import requests

        url = "https://data.hexin.cn/market/hsgtApi/method/dayChart/"
        headers = {
            "User-Agent": _THS_UA,
            "Host": "data.hexin.cn",
            "Referer": "https://data.hexin.cn/",
        }

        try:
            r = requests.get(url, headers=headers, timeout=10)
            d = r.json()
        except Exception as e:
            log_error(f"ths north_money_realtime error: {e}")
            return None

        times = d.get("time", [])
        hgt = d.get("hgt", [])
        sgt = d.get("sgt", [])
        n = len(times)

        rows = []
        for i in range(n):
            rows.append({
                "time": times[i],
                "hgt_yi": hgt[i] if i < len(hgt) else None,
                "sgt_yi": sgt[i] if i < len(sgt) else None,
            })
        return rows


# 单例
_instance: Optional[THSProvider] = None


def get_ths_provider() -> THSProvider:
    global _instance
    if _instance is None:
        _instance = THSProvider()
    return _instance
