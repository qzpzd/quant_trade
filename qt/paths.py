"""应用根目录：开发态与 PyInstaller 打包态统一。"""

from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    """可执行文件旁（含 web/、data_cache/）为根目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_dir(*parts: str) -> Path:
    """优先 exe 旁；若无则尝试 _MEIPASS（onefile 解压目录）。"""
    root = app_root()
    p = root.joinpath(*parts)
    if p.exists():
        return p
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        alt = Path(meipass).joinpath(*parts)
        if alt.exists():
            return alt
    return p
