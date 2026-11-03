"""
形迹 QuantTrade 桌面启动器。

双击后启动本地 Web 服务并打开浏览器；关闭窗口即停止。
开发：python desktop_launcher.py
"""

from __future__ import annotations

import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path


HOST = "127.0.0.1"
PORT = 8765


def _base() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _pick_port(preferred: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((HOST, preferred))
            return preferred
        except OSError:
            s.bind((HOST, 0))
            return int(s.getsockname()[1])


def _popup(title: str, msg: str, error: bool = False) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        if error:
            messagebox.showerror(title, msg)
        else:
            messagebox.showinfo(title, msg)
        root.destroy()
    except Exception:
        print(msg)


def _ensure_paths() -> Path:
    base = _base()
    web = base / "web"
    if not web.is_dir():
        raise FileNotFoundError(
            f"未找到 web/ 目录。\n请将本程序与 web/、data_cache/ 放在同一文件夹。\n当前：{base}"
        )
    (base / "data_cache" / "bars").mkdir(parents=True, exist_ok=True)
    (base / "data_cache" / "auction").mkdir(parents=True, exist_ok=True)
    # 保证导入 qt 时 ROOT 指向 exe 旁
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))
    return base


def _run_server(port: int):
    import uvicorn

    # 延迟导入，确保 sys.path / frozen 根目录已就绪
    from server import app

    config = uvicorn.Config(
        app,
        host=HOST,
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    server.run()
    return server


def main() -> None:
    try:
        base = _ensure_paths()
    except Exception as exc:
        _popup("形迹 QuantTrade", str(exc), error=True)
        sys.exit(1)

    port = _pick_port(PORT)
    url = f"http://{HOST}:{port}/"

    server_holder: dict = {}

    def boot():
        try:
            import uvicorn
            from server import app

            config = uvicorn.Config(app, host=HOST, port=port, log_level="warning", access_log=False)
            server = uvicorn.Server(config)
            server_holder["server"] = server
            server.run()
        except Exception as exc:
            server_holder["error"] = str(exc)

    th = threading.Thread(target=boot, daemon=True)
    th.start()

    # 等服务起来
    ok = False
    for _ in range(60):
        if server_holder.get("error"):
            break
        try:
            with socket.create_connection((HOST, port), timeout=0.3):
                ok = True
                break
        except OSError:
            time.sleep(0.25)

    if not ok:
        err = server_holder.get("error") or "服务启动超时"
        _popup("形迹 QuantTrade", f"无法启动 Web 服务：{err}", error=True)
        sys.exit(1)

    try:
        import tkinter as tk

        root = tk.Tk()
        root.title("形迹 QuantTrade")
        root.geometry("460x240")
        root.resizable(False, False)

        tk.Label(root, text="服务运行中", font=("Microsoft YaHei", 14)).pack(pady=(20, 4))
        tk.Label(root, text=url, fg="#0a5").pack()
        tk.Label(root, text=str(base), wraplength=420, fg="#666", font=("", 9)).pack(pady=8)
        tk.Label(
            root,
            text="含 Web 界面与本地行情缓存。关闭本窗口即停止服务。\n不含微信小程序。",
            fg="#444",
            font=("", 9),
        ).pack()

        def open_home():
            webbrowser.open(url)

        btn = tk.Frame(root)
        btn.pack(pady=12)
        tk.Button(btn, text="打开浏览器", width=14, command=open_home).grid(row=0, column=0, padx=6)
        tk.Button(btn, text="退出", width=10, command=root.destroy).grid(row=0, column=1, padx=6)

        root.protocol("WM_DELETE_WINDOW", root.destroy)
        open_home()
        root.mainloop()
    except Exception:
        webbrowser.open(url)
        print(f"已打开 {url} ，按 Ctrl+C 结束")
        try:
            while th.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
