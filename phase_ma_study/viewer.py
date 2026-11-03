"""
实时大屏查看服务：扫描 stocks/ 目录，浏览器自动刷新跟随新图。

  .\\.venv\\Scripts\\python.exe -m phase_ma_study.viewer
  浏览器打开 http://127.0.0.1:8770/
"""

from __future__ import annotations

import argparse
import json
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from phase_ma_study.catalog import scan_catalog, write_catalog  # noqa: E402
from phase_ma_study.config import DEFAULT_OUTPUT  # noqa: E402
from phase_ma_study.dashboard import write_live_dashboard  # noqa: E402


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, output_dir: Path, **kwargs):
        self.output_dir = Path(output_dir)
        super().__init__(*args, directory=str(self.output_dir), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/api/catalog", "/api/catalog/"):
            cat = scan_catalog(self.output_dir)
            body = json.dumps(cat, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path in ("/", "/index.html"):
            # 保证 dashboard 为最新动态壳
            write_live_dashboard(self.output_dir, refresh_catalog=False)
            self.path = "/dashboard.html"
        return super().do_GET()

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="阶段图库实时大屏")
    ap.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT))
    ap.add_argument("--host", type=str, default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8770)
    args = ap.parse_args(argv)

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    write_live_dashboard(out, refresh_catalog=True)
    write_catalog(out)

    handler = partial(Handler, output_dir=out)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"大屏: http://{args.host}:{args.port}/")
    print(f"目录: {out}")
    print("页面每 8 秒自动扫描 stocks/ 下新图片。Ctrl+C 结束。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
