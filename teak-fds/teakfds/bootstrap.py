"""确保技能根目录在 sys.path 上（拷贝到 Agent skills 后可直接 import teakfds）。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

_SKILL_ROOT: Optional[Path] = None


def skill_root() -> Path:
    """teak-fds 目录（含 pyproject.toml / SKILL.md 的父级）。"""
    global _SKILL_ROOT
    if _SKILL_ROOT is None:
        _SKILL_ROOT = Path(__file__).resolve().parent.parent
    return _SKILL_ROOT


def ensure_skill_path() -> Path:
    root = skill_root()
    root_s = str(root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    return root
