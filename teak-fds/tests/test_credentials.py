"""凭证路径解析（离线）。"""

from pathlib import Path

from teakfds.credentials import (
    iwencai_cookie_path,
    load_xueqiu_cookie_header,
    xueqiu_cookies_path,
)


def test_xueqiu_path_under_agents_documents():
    p = xueqiu_cookies_path()
    assert "agents_documents" in str(p)
    if p.is_file():
        assert load_xueqiu_cookie_header()


def test_iwencai_path():
    p = iwencai_cookie_path()
    assert p.name == "IWENCAI_API_KEY.txt"
