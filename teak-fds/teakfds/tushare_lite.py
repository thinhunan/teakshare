#!/usr/bin/env python3
"""
Tushare Pro HTTP 客户端（不依赖 tushare 包）

- 单端点 POST https://api.tushare.pro，与官方 SDK 一致
- 返回 list[dict]（与官方 SDK 列名一致），不依赖 pandas
"""

from __future__ import annotations

import json
import os
from functools import partial
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

# 与 TushareProvider 一致，便于共用 token 查找逻辑
TUSHARE_API_URL = "https://api.tushare.pro"

DEFAULT_TOKEN_PATHS = [
    Path.home() / "agents_documents" / "TUSHARE_TOKEN.txt",
    Path.home() / ".openclaw" / "credentials" / "TUSHARE_TOKEN.txt",
    Path.home() / ".tushare" / "token.txt",
    Path.home() / ".tushare_token",
]


def load_tushare_token(
    extra_paths: Optional[List[Path]] = None,
    explicit: Optional[str] = None,
) -> Optional[str]:
    """读取 TUSHARE_TOKEN：显式 > 环境变量 > 已知路径文件。"""
    if explicit:
        t = explicit.strip()
        return t or None
    t = os.environ.get("TUSHARE_TOKEN")
    if t and str(t).strip():
        return str(t).strip()
    paths = list(DEFAULT_TOKEN_PATHS)
    if extra_paths:
        paths.extend(extra_paths)
    for p in paths:
        try:
            if p.exists():
                content = p.read_text(encoding="utf-8", errors="ignore").strip()
                if content:
                    return content
        except OSError:
            continue
    return None


class TushareHttpClient:
    """底层 HTTP：query_raw / query_records"""

    def __init__(self, token: str, timeout: float = 60.0):
        self._token = token.strip()
        self._timeout = timeout
        self._url = TUSHARE_API_URL
        self._session = requests.Session()

    def query_raw(self, api_name: str, fields: str = "", **params: Any) -> Tuple[List[str], List[Any]]:
        req_body: Dict[str, Any] = {
            "api_name": api_name,
            "token": self._token,
            "params": params,
            "fields": fields if fields is not None else "",
        }
        resp = self._session.post(self._url, json=req_body, timeout=self._timeout)
        resp.raise_for_status()
        try:
            result = resp.json()
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Tushare API 非 JSON 响应: {resp.text[:500]}") from e

        code = result.get("code")
        if code != 0:
            msg = result.get("msg") or result.get("message") or str(result)
            raise RuntimeError(f"Tushare API error code={code}: {msg}")

        data = result.get("data")
        if data is None:
            return [], []
        fields_list = data.get("fields") or []
        items = data.get("items") or []
        return fields_list, items

    def query_records(
        self, api_name: str, fields: str = "", **params: Any
    ) -> List[Dict[str, Any]]:
        cols, items = self.query_raw(api_name, fields, **params)
        if not items:
            return []
        if not cols:
            return []
        return [dict(zip(cols, row)) for row in items]

class TushareHttpDataApi:
    """
    模拟 tushare client.DataApi：支持 pro.daily(...) 与 pro.query('daily', ...)
    """

    def __init__(self, client: TushareHttpClient):
        self._client = client

    def query(self, api_name: str, fields: str = "", **kwargs: Any) -> Any:
        return self._client.query_records(api_name, fields, **kwargs)

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)

        def _method(*args: Any, **kwargs: Any) -> Any:
            if args:
                raise TypeError(
                    f"Tushare API {name}() does not accept positional arguments"
                )
            fields = kwargs.pop("fields", "") or ""
            return self._client.query_records(name, fields, **kwargs)

        return _method


def create_pro_api(token: Optional[str] = None) -> Optional[TushareHttpDataApi]:
    """等价于 ts.pro_api(token)，失败返回 None。"""
    tok = load_tushare_token(explicit=token)
    if not tok:
        return None
    return TushareHttpDataApi(TushareHttpClient(tok))


# 兼容旧名
TushareLite = TushareHttpClient

_lite_singleton: Optional[TushareHttpDataApi] = None


def get_tushare_lite(token: Optional[str] = None) -> Optional[TushareHttpDataApi]:
    """获取单例 DataApi（可选传入 token 覆盖）。"""
    global _lite_singleton
    if token:
        return create_pro_api(token)
    if _lite_singleton is not None:
        return _lite_singleton
    _lite_singleton = create_pro_api()
    return _lite_singleton
