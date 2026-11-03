"""
便携启动器：双击打开同目录（或 data/）下的 dashboard.html。
打包进 PhaseMAGallery 文件夹后，换电脑解压即可用。
"""

from __future__ import annotations

import sys
import webbrowser
from pathlib import Path


def resolve_dashboard() -> Path:
    # PyInstaller 运行时
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent / "output"

    candidates = [
        base / "dashboard.html",
        base / "data" / "dashboard.html",
        base / "output" / "dashboard.html",
    ]
    for p in candidates:
        if p.is_file():
            return p
    raise FileNotFoundError(
        "未找到 dashboard.html。请将本程序与 data/（含 dashboard.html 与 stocks/）放在同一目录。"
    )


def main() -> None:
    try:
        dash = resolve_dashboard()
    except FileNotFoundError as e:
        # 尽量弹窗；无 tk 则打印
        msg = str(e)
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("PhaseMAGallery", msg)
            root.destroy()
        except Exception:
            print(msg)
            input("按回车退出…")
        sys.exit(1)

    # file:// URI
    uri = dash.resolve().as_uri()
    webbrowser.open(uri)


if __name__ == "__main__":
    main()
