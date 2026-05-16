#!/usr/bin/env python3
"""
统一数据源日志模块

FDS 内部完整实现，不依赖外部 team/utils 目录。

功能:
1. 外呼请求日志 → ~/.openclaw/logs/dataproxy/dataproxy.log (JSON行格式，RotatingFileHandler)；
   含 ``params``（脱敏后的请求参数）、可选 ``caller``（封装入口），失败时同样记录便于定位。
2. 内部日志 (Provider注册/状态等) → stderr (不污染 stdout)
"""

from __future__ import annotations

import json
import logging
import sys
import threading
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Optional


# ========== 日志目录 ==========

# 键名包含以下子串时，值记为占位符（避免 token/密码进日志）
_SENSITIVE_KEY_FRAGMENTS = (
    "password",
    "passwd",
    "token",
    "secret",
    "apikey",
    "api_key",
    "authorization",
    "cookie",
    "jwt",
)


def _is_sensitive_key(key: str) -> bool:
    k = (key or "").lower()
    return any(frag in k for frag in _SENSITIVE_KEY_FRAGMENTS)


def sanitize_for_log(
    obj: Any,
    *,
    max_depth: int = 10,
    max_str: int = 4000,
    _depth: int = 0,
) -> Any:
    """
    将请求参数等结构脱敏并截断，便于写入 JSON 行日志。
    支持 dict/list/tuple/基本类型；过深嵌套用占位符截断。
    """
    if _depth > max_depth:
        return "<max_depth>"
    if obj is None:
        return None
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, (int, float)):
        return obj
    if isinstance(obj, str):
        s = obj
        if len(s) > max_str:
            return s[:max_str] + "…(truncated)"
        return s
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            ks = str(k)
            if _is_sensitive_key(ks):
                out[ks] = "<redacted>"
            else:
                out[ks] = sanitize_for_log(v, max_depth=max_depth, max_str=max_str, _depth=_depth + 1)
        return out
    if isinstance(obj, (list, tuple)):
        seq = list(obj)
        if len(seq) > 200:
            seq = seq[:200] + ["<truncated_list>"]
        return [
            sanitize_for_log(x, max_depth=max_depth, max_str=max_str, _depth=_depth + 1)
            for x in seq
        ]
    return str(obj)[:max_str]


def _compact_params_for_record(params: Any, max_json_chars: int = 12000) -> Any:
    """写入单条日志记录时的 params 字段：脱敏 + 总长度上限。"""
    try:
        cleaned = sanitize_for_log(params)
        s = json.dumps(cleaned, ensure_ascii=False)
        if len(s) <= max_json_chars:
            return cleaned
        return {
            "_truncated": True,
            "preview": s[: max_json_chars - 80] + "…",
        }
    except Exception:
        return str(params)[:2000]


# ========== 日志目录 ==========

def log_dir() -> Path:
    return Path.home() / ".openclaw" / "logs" / "dataproxy"


# ========== 文件日志（外呼请求） ==========

_LOG_LOCK = threading.Lock()
_CONFIGURED = False


def _ensure_logger() -> logging.Logger:
    """确保文件日志器已配置"""
    global _CONFIGURED
    with _LOG_LOCK:
        if _CONFIGURED:
            return logging.getLogger("openclaw.datasource")
        d = log_dir()
        d.mkdir(parents=True, exist_ok=True)
        log = logging.getLogger("openclaw.datasource")
        log.setLevel(logging.INFO)
        log.handlers.clear()
        fh = RotatingFileHandler(
            d / "dataproxy.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        fh.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(fh)
        log.propagate = False
        _CONFIGURED = True
        return log


def log_external_request(
    *,
    provider: str,
    method: str,
    url: str,
    action: str = "",
    success: bool = True,
    status_code: Optional[int] = None,
    message: str = "",
    symbol: Optional[str] = None,
    duration_ms: Optional[float] = None,
    params: Optional[Any] = None,
    caller: Optional[str] = None,
) -> None:
    """记录一次对外 HTTP(S) 请求或等价远端调用。

    Args:
        params: 请求参数摘要（如 POST JSON、GET query dict、Tushare kwargs），会经 ``sanitize_for_log`` 脱敏后写入。
        caller: 可选，上层封装标识（如 ``TushareProvider.pro_call``），便于与 ``action`` 区分。
    """
    try:
        log = _ensure_logger()
        rec: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "provider": provider,
            "method": method.upper(),
            "url": (url or "")[:4000],
            "action": action or "",
            "success": success,
            "status_code": status_code,
            "symbol": symbol,
            "duration_ms": round(duration_ms, 3) if duration_ms is not None else None,
            "message": (message or "")[:2000],
        }
        if caller:
            rec["caller"] = (caller or "")[:500]
        if params is not None:
            rec["params"] = _compact_params_for_record(params)
        log.info(json.dumps(rec, ensure_ascii=False))
    except Exception:
        pass


# ========== 兼容性日志器（Xueqiu/Generic） ==========

class XueqiuDatasourceLogger:
    """与历史 xueqiu_client 兼容的薄封装。"""

    def log_request(
        self,
        action: str,
        symbol: Any = None,
        success: bool = True,
        message: str = "",
        url: Optional[str] = None,
        status_code: Optional[int] = None,
        duration_ms: Optional[float] = None,
        params: Optional[Any] = None,
    ) -> None:
        log_external_request(
            provider="xueqiu",
            method="GET",
            url=url or f"https://xueqiu.com/_/{action}",
            action=action,
            symbol=str(symbol) if symbol is not None else None,
            success=success,
            status_code=status_code,
            duration_ms=duration_ms,
            message=message,
            params=params,
        )

    def log_error(
        self,
        action: str,
        error: BaseException,
        symbol: Any = None,
        url: Optional[str] = None,
        params: Optional[Any] = None,
    ) -> None:
        log_external_request(
            provider="xueqiu",
            method="GET",
            url=url or f"https://xueqiu.com/_/{action}",
            action=action,
            symbol=str(symbol) if symbol is not None else None,
            success=False,
            message=f"{type(error).__name__}: {error}",
            params=params,
        )


_xueqiu_singleton: Optional[XueqiuDatasourceLogger] = None


def get_xueqiu_logger() -> XueqiuDatasourceLogger:
    global _xueqiu_singleton
    if _xueqiu_singleton is None:
        _xueqiu_singleton = XueqiuDatasourceLogger()
    return _xueqiu_singleton


class GenericDatasourceLogger:
    """通用数据源日志器。"""

    def __init__(self, provider: str):
        self.provider = provider

    def log_request(
        self,
        action: str,
        symbol: Any = None,
        success: bool = True,
        message: str = "",
        url: Optional[str] = None,
        status_code: Optional[int] = None,
        duration_ms: Optional[float] = None,
        params: Optional[Any] = None,
    ) -> None:
        log_external_request(
            provider=self.provider,
            method="GET",
            url=url or f"https://{self.provider}.com/_/{action}",
            action=action,
            symbol=str(symbol) if symbol is not None else None,
            success=success,
            status_code=status_code,
            duration_ms=duration_ms,
            message=message,
            params=params,
        )

    def log_error(
        self,
        action: str,
        error: BaseException,
        symbol: Any = None,
        url: Optional[str] = None,
        params: Optional[Any] = None,
    ) -> None:
        log_external_request(
            provider=self.provider,
            method="GET",
            url=url or f"https://{self.provider}.com/_/{action}",
            action=action,
            symbol=str(symbol) if symbol is not None else None,
            success=False,
            message=f"{type(error).__name__}: {error}",
            params=params,
        )


def get_tushare_logger() -> GenericDatasourceLogger:
    return GenericDatasourceLogger("tushare")


def get_akshare_logger() -> GenericDatasourceLogger:
    return GenericDatasourceLogger("akshare")


def get_mx_logger() -> GenericDatasourceLogger:
    return GenericDatasourceLogger("mx")


# ========== 内部日志（Provider 注册/状态等） → stderr ==========

def log_info(msg: object = "") -> None:
    """信息日志 → stderr"""
    print(msg, file=sys.stderr)


def log_warn(msg: object = "") -> None:
    """警告日志 → stderr"""
    print(msg, file=sys.stderr)


def log_error(msg: object = "") -> None:
    """错误日志 → stderr"""
    print(msg, file=sys.stderr)


def log_debug(msg: object = "") -> None:
    """调试日志 → stderr"""
    print(msg, file=sys.stderr)
