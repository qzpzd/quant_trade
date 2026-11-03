"""
阶段图库 Web 端：本地 HTTP 服务 + 浏览器。

双击 PhaseMAWeb.exe 后：
  - 在同目录托管 dashboard.html / correlation.html / stocks/
  - 打开 http://127.0.0.1:8770/
  - 关闭窗口即停止服务

开发：
  python -m phase_ma_study.web_launcher
"""

from __future__ import annotations

import socket
import sys
import threading
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


def resolve_output() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent / "output"


def pick_port(host: str, preferred: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, preferred))
            return preferred
        except OSError:
            s.bind((host, 0))
            return int(s.getsockname()[1])


INDEX_HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head>
<meta charset="utf-8"/>
<title>阶段图库 Web</title>
<style>
body{font-family:"Segoe UI","Microsoft YaHei",sans-serif;background:#0e100c;color:#efe7d6;
margin:0;padding:48px 24px;line-height:1.6}
a{color:#e6ff4a;text-decoration:none}
.card{max-width:520px;margin:0 auto;background:#161910;border:1px solid #2c3224;
border-radius:10px;padding:28px}
h1{margin:0 0 8px;font-size:22px;color:#e6ff4a}
p{color:#8b8473;font-size:13px}
ul{padding-left:18px}
li{margin:10px 0;font-size:16px}
</style></head><body>
<div class="card">
<h1>阶段图库 Web</h1>
<p>本地服务已启动。关闭启动窗口即停止。</p>
<ul>
<li><a href="/dashboard.html">阶段大屏</a></li>
<li><a href="/correlation.html">指标相关与买卖点</a></li>
<li><a href="/reports/买卖点与选股Prompt手册.md">选股手册（文本）</a></li>
</ul>
</div>
</body></html>
"""


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, output_dir: Path, **kwargs):
        self.output_dir = Path(output_dir)
        super().__init__(*args, directory=str(self.output_dir), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            body = INDEX_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()

    def log_message(self, fmt, *args):
        pass


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


def run_ui(host: str, port: int, out: Path, server: ThreadingHTTPServer) -> None:
    import tkinter as tk

    root = tk.Tk()
    root.title("阶段图库 Web")
    root.geometry("420x220")
    root.resizable(False, False)

    url = f"http://{host}:{port}/"
    tk.Label(root, text="服务运行中", font=("Microsoft YaHei", 14)).pack(pady=(18, 4))
    tk.Label(root, text=url, fg="#0a5").pack()
    tk.Label(root, text=str(out), wraplength=380, fg="#666").pack(pady=6)

    def open_page(path: str = "/") -> None:
        webbrowser.open(url.rstrip("/") + path)

    btn = tk.Frame(root)
    btn.pack(pady=8)
    tk.Button(btn, text="打开首页", width=12, command=lambda: open_page("/")).grid(row=0, column=0, padx=4)
    tk.Button(btn, text="阶段大屏", width=12, command=lambda: open_page("/dashboard.html")).grid(
        row=0, column=1, padx=4
    )
    tk.Button(btn, text="相关分析", width=12, command=lambda: open_page("/correlation.html")).grid(
        row=0, column=2, padx=4
    )

    def on_close() -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()
        root.destroy()

    tk.Button(root, text="退出并停止服务", command=on_close).pack(pady=6)
    root.protocol("WM_DELETE_WINDOW", on_close)
    open_page("/")
    root.mainloop()


def main() -> None:
    out = resolve_output()
    dash = out / "dashboard.html"
    if not dash.is_file():
        _popup(
            "阶段图库 Web",
            f"未找到 dashboard.html。\n请把本程序放在含 dashboard.html 与 stocks/ 的目录里。\n当前：{out}",
            error=True,
        )
        sys.exit(1)

    host = "127.0.0.1"
    port = pick_port(host, 8770)
    handler = partial(Handler, output_dir=out)
    server = ThreadingHTTPServer((host, port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        run_ui(host, port, out, server)
    finally:
        try:
            server.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    main()
