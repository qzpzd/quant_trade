"""Scan cached bars for recent buy/sell setups shown on the home page."""

from __future__ import annotations

import json
from datetime import datetime

import pandas as pd

from qt.config import CACHE_DIR
from qt.data import list_cached_symbols, load_cached_bars, load_universe, stock_name
from qt.signals import current_view

ALERTS_PATH = CACHE_DIR / "alerts.json"


def _age_days(last: pd.Timestamp, date_str: str) -> int:
    return int((last.normalize() - pd.Timestamp(date_str).normalize()).days)


def evaluate_symbol(symbol: str, name: str | None = None) -> dict | None:
    df = load_cached_bars(symbol)
    if df is None or len(df) < 60:
        return None
    if len(df) > 160:
        df = df.iloc[-160:]
    try:
        view = current_view(df)
    except Exception:
        return None
    last = pd.Timestamp(df.index[-1])
    snap = view.get("snapshot") or {}
    buys, sells = [], []
    for s in view.get("signals") or []:
        age = _age_days(last, s["date"])
        if age < 0 or age > 3:
            continue
        (buys if s["action"] == "buy" else sells).append({**s, "age": age})
    for s in view.get("latest_reasons") or []:
        if "date" in s:
            continue
        if s.get("action") == "buy":
            buys.append({**s, "date": last.strftime("%Y-%m-%d"), "age": 0, "price": snap.get("close")})
        elif s.get("action") == "sell":
            sells.append({**s, "date": last.strftime("%Y-%m-%d"), "age": 0, "price": snap.get("close")})

    kind = None
    if view.get("stance_id") == "buy" and buys:
        kind = "buy"
    elif view.get("stance_id") == "sell" and sells:
        kind = "sell"
    elif len(buys) >= 2 and (view.get("score") or 0) >= 0.2:
        kind = "buy"
    elif len(sells) >= 2 and (view.get("score") or 0) <= -0.2:
        kind = "sell"
    elif buys and min(b["age"] for b in buys) == 0 and (view.get("score") or 0) >= 0.35:
        kind = "buy"
    elif sells and min(s["age"] for s in sells) == 0 and (view.get("score") or 0) <= -0.35:
        kind = "sell"
    if not kind:
        return None

    reasons = buys if kind == "buy" else sells
    uniq = []
    seen = set()
    for r in reasons:
        key = (r.get("source"), r.get("reason"))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)
    return {
        "symbol": symbol,
        "name": name or stock_name(symbol),
        "kind": kind,
        "stance": view.get("stance"),
        "regime": view.get("regime"),
        "score": view.get("score"),
        "close": snap.get("close"),
        "rsi14": snap.get("rsi14"),
        "as_of": last.strftime("%Y-%m-%d"),
        "reasons": [
            {
                "source": r.get("source"),
                "reason": r.get("reason"),
                "date": r.get("date"),
            }
            for r in uniq[:4]
        ],
    }


def scan_alerts(universe_key: str = "low20", progress: dict | None = None) -> dict:
    try:
        members = load_universe(universe_key, refresh=False)
        names = {m["symbol"]: m.get("name") for m in members}
        pool = [m["symbol"] for m in members]
    except Exception:
        names, pool = {}, list_cached_symbols()
    cached = set(list_cached_symbols())
    symbols = [s for s in pool if s in cached]
    total = len(symbols)
    if progress is not None:
        progress.update({"phase": "alerts", "scan_done": 0, "scan_total": total})

    buys, sells = [], []
    for i, code in enumerate(symbols, 1):
        hit = evaluate_symbol(code, names.get(code))
        if hit:
            (buys if hit["kind"] == "buy" else sells).append(hit)
        if progress is not None and (i % 5 == 0 or i == total):
            progress["scan_done"] = i
            progress["done"] = i
            progress["total"] = total

    buys.sort(key=lambda x: (x.get("score") or 0, len(x["reasons"])), reverse=True)
    sells.sort(key=lambda x: (x.get("score") or 0, -len(x["reasons"])))
    payload = {
        "scanned_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "universe": universe_key,
        "scanned": total,
        "buys": buys[:30],
        "sells": sells[:20],
    }
    ALERTS_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    if progress is not None:
        progress["scan_done"] = total
        progress["alert_buys"] = len(payload["buys"])
        progress["alert_sells"] = len(payload["sells"])
    return payload


def load_alerts() -> dict:
    if not ALERTS_PATH.exists():
        return {"scanned_at": None, "scanned": 0, "buys": [], "sells": []}
    return json.loads(ALERTS_PATH.read_text(encoding="utf-8"))


def watchlist_alerts() -> dict:
    from qt.watchlist import watch_symbols

    data = load_alerts()
    watched = watch_symbols()
    buys = [a for a in (data.get("buys") or []) if a.get("symbol") in watched]
    sells = [a for a in (data.get("sells") or []) if a.get("symbol") in watched]
    return {
        "scanned_at": data.get("scanned_at"),
        "watched": len(watched),
        "buys": buys,
        "sells": sells,
        "items": buys + sells,
    }
