# -*- coding: utf-8 -*-
import json
import urllib.error
import urllib.request

bases = ["http://127.0.0.1:8765", "http://192.168.3.202:8765"]


def req(base, method, path, body=None, timeout=120):
    data = None if body is None else json.dumps(body).encode("utf-8")
    r = urllib.request.Request(
        base + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        raw = resp.read()
        return resp.status, json.loads(raw.decode("utf-8"))


def main():
    for base in bases:
        print("====", base)
        try:
            st, h = req(base, "GET", "/api/health")
            print("health", st, h)
        except Exception as e:
            print("health FAIL", e)
            continue

        gets = [
            "/api/strategies",
            "/api/watchlist",
            "/api/alerts",
            "/api/cache/status",
            "/api/dashboard",
            "/api/quote/002195?start=2024-01-01",
            "/api/analyze/002195?start=2024-01-01",
            "/api/search?q=002195",
            "/api/screen/fields",
            "/api/screens",
            "/api/patterns",
            "/api/calendar?year=2026&month=9&live=0",
            "/api/auction/002195",
        ]
        for path in gets:
            try:
                st, data = req(base, "GET", path, timeout=60)
                keys = list(data.keys())[:8] if isinstance(data, dict) else type(data).__name__
                print("OK", path, st, keys)
            except Exception as e:
                print("FAIL", path, e)

        posts = [
            (
                "/api/backtest",
                {
                    "symbol": "002195",
                    "strategies": ["trend"],
                    "start": "2023-01-01",
                    "end": "2024-06-30",
                    "cash": 100000,
                },
            ),
            ("/api/predict", {"symbol": "002195", "lookback": 30, "horizon": 10}),
            (
                "/api/screen",
                {
                    "universe": "demo",
                    "conditions": [{"field": "rsi14", "op": "<", "value": 40}],
                    "limit": 10,
                },
            ),
            (
                "/api/similar",
                {
                    "symbol": "002195",
                    "start": "2024-06-01",
                    "end": "2024-08-01",
                    "universe": "demo",
                    "top_n": 5,
                    "lookback_days": 60,
                    "include_current": True,
                    "analyze": True,
                },
            ),
        ]
        for path, body in posts:
            try:
                st, data = req(base, "POST", path, body, timeout=180)
                extra = ""
                if path.endswith("backtest"):
                    extra = f" results={data.get('count')} ret={(data.get('primary') or {}).get('return_pct')}"
                elif path.endswith("predict"):
                    extra = f" bias={data.get('bias')} n={data.get('n_analogs')}"
                elif path.endswith("screen"):
                    extra = f" hits={data.get('count')}"
                elif path.endswith("similar"):
                    extra = f" keys={list(data.keys())[:10]}"
                    for k in ("matches", "picks", "hits", "table", "results"):
                        if k in data and isinstance(data[k], list):
                            extra += f" {k}={len(data[k])}"
                print("OK", path, st, extra)
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", errors="ignore")[:240]
                print("FAIL", path, f"HTTP {e.code}", detail)
            except Exception as e:
                print("FAIL", path, e)


if __name__ == "__main__":
    main()
