"""巨潮 webapi 投资评级（纯 Python AES，无 akshare / py_mini_racer）。"""

from __future__ import annotations

import base64
import time
from typing import Any, Dict, List, Optional

import requests

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad

    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False


def _cninfo_accept_enckey() -> Optional[str]:
    """等价 cninfo.js getResCode1()。"""
    if not _HAS_CRYPTO:
        return None
    ts = str(int(time.time()))
    key = b"1234567887654321"
    iv = b"1234567887654321"
    cipher = AES.new(key, AES.MODE_CBC, iv)
    ct = cipher.encrypt(pad(ts.encode("utf-8"), 16))
    return base64.b64encode(ct).decode("ascii")


def fetch_rating_forecast_cninfo(date: str) -> Optional[List[Dict[str, Any]]]:
    """
    巨潮投资评级列表。

    Args:
        date: YYYYMMDD
    """
    enc = _cninfo_accept_enckey()
    if not enc:
        return None
    d = (date or "").replace("-", "")
    if len(d) != 8:
        return None
    tdate = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    url = "http://webapi.cninfo.com.cn/api/sysapi/p_sysapi1089"
    headers = {
        "Accept": "*/*",
        "Accept-Enckey": enc,
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Content-Length": "0",
        "Host": "webapi.cninfo.com.cn",
        "Origin": "http://webapi.cninfo.com.cn",
        "Referer": "http://webapi.cninfo.com.cn/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "X-Requested-With": "XMLHttpRequest",
    }
    try:
        r = requests.post(url, params={"tdate": tdate}, headers=headers, timeout=20)
        r.raise_for_status()
        records = (r.json() or {}).get("records") or []
    except Exception:
        return None
    if not records:
        return None
    out: List[Dict[str, Any]] = []
    for row in records:
        out.append(
            {
                "证券代码": row.get("zqdm") or row.get("SEC_CODE"),
                "证券简称": row.get("zqjc") or row.get("SEC_NAME"),
                "发布日期": row.get("fbrq") or row.get("PUBLISH_DATE"),
                "研究机构简称": row.get("orgname") or row.get("ORG_NAME"),
                "研究员名称": row.get("author") or row.get("AUTHOR"),
                "投资评级": row.get("rating") or row.get("RATING"),
                "是否首次评级": row.get("sfsqpj"),
                "评级变化": row.get("ratingchg"),
                "前一次投资评级": row.get("prerating"),
                "目标价格-下限": row.get("mbjxx"),
                "目标价格-上限": row.get("mbjsx"),
            }
        )
    return out
