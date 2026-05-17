"""统一凭证路径（~/agents_documents 与 ~/.openclaw/credentials）。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

_AGENTS = Path.home() / "agents_documents"
_OPENCLAW_CRED = Path.home() / ".openclaw" / "credentials"


def _read_first_line(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return None
        return text.splitlines()[0].strip()
    except OSError:
        return None


def _resolve_file(name: str, extra: Optional[List[Path]] = None) -> Optional[Path]:
    candidates = list(extra or []) + [
        _AGENTS / name,
        _OPENCLAW_CRED / name,
    ]
    for p in candidates:
        if p.is_file() and p.stat().st_size > 0:
            return p
    return None


def load_text_credential(name: str, env_var: Optional[str] = None) -> Optional[str]:
    """读凭证文件首行；环境变量优先。"""
    if env_var:
        v = os.environ.get(env_var)
        if v and v.strip():
            return v.strip()
    p = _resolve_file(name)
    if p:
        return _read_first_line(p)
    return None


# --- 公开路径 ---

def tushare_token_paths() -> List[Path]:
    return [
        _AGENTS / "TUSHARE_TOKEN.txt",
        _OPENCLAW_CRED / "TUSHARE_TOKEN.txt",
        Path.home() / ".tushare" / "token.txt",
    ]


def xueqiu_cookies_path() -> Path:
    return _resolve_file("xueqiu_cookies.txt") or (_AGENTS / "xueqiu_cookies.txt")


def iwencai_cookie_path() -> Path:
    """问财 Cookie（pywencai 的 cookie 参数）；文件常为浏览器 Cookie 头或 hexin 相关。"""
    return _resolve_file("IWENCAI_API_KEY.txt") or (_AGENTS / "IWENCAI_API_KEY.txt")


def mx_apikey_path() -> Path:
    return _resolve_file("MX_APIKEY.txt") or (_AGENTS / "MX_APIKEY.txt")


def load_tushare_token() -> Optional[str]:
    return load_text_credential("TUSHARE_TOKEN.txt", "TUSHARE_TOKEN")


def load_mx_apikey() -> Optional[str]:
    return load_text_credential("MX_APIKEY.txt", "MX_APIKEY")


def load_xueqiu_cookie_header() -> str:
    p = xueqiu_cookies_path()
    if not p.is_file():
        return ""
    return p.read_text(encoding="utf-8").strip()


def load_iwencai_cookie() -> Optional[str]:
    """问财：整文件内容作为 cookie 头（与 IWENCAI_API_KEY.txt 命名历史一致）。"""
    p = iwencai_cookie_path()
    if not p.is_file():
        return None
    text = p.read_text(encoding="utf-8").strip()
    return text or None
