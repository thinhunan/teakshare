"""东财 datacenter-web 通用请求（无 akshare 依赖）。"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import requests

_EM_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_EM_REFERER = "https://data.eastmoney.com/"
_DC_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"


def em_get(
    *,
    report_name: str,
    columns: str = "ALL",
    filter_expr: str = "",
    page_size: int = 500,
    page_number: int = 1,
    sort_columns: str = "",
    sort_types: str = "",
    timeout: float = 20.0,
) -> List[Dict[str, Any]]:
    params: Dict[str, str] = {
        "reportName": report_name,
        "columns": columns,
        "pageNumber": str(page_number),
        "pageSize": str(page_size),
        "source": "WEB",
        "client": "WEB",
    }
    if filter_expr:
        params["filter"] = filter_expr
    if sort_columns:
        params["sortColumns"] = sort_columns
    if sort_types:
        params["sortTypes"] = sort_types
    headers = {"User-Agent": _EM_UA, "Referer": _EM_REFERER}
    resp = requests.get(_DC_URL, params=params, headers=headers, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("success"):
        return []
    result = payload.get("result") or {}
    return list(result.get("data") or [])


def em_get_all_pages(
    *,
    report_name: str,
    filter_expr: str = "",
    page_size: int = 500,
    max_pages: int = 20,
    **kwargs: Any,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        chunk = em_get(
            report_name=report_name,
            filter_expr=filter_expr,
            page_size=page_size,
            page_number=page,
            **kwargs,
        )
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < page_size:
            break
        time.sleep(0.15)
    return rows
