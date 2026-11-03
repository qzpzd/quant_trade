"""Persisted watchlist shared by homepage, drawer, and popup alerts."""

from __future__ import annotations

import json
from datetime import datetime

from qt.config import CACHE_DIR
from qt.data import normalize_symbol, stock_name

WATCH_PATH = CACHE_DIR / "watchlist.json"


def load_watchlist() -> list[dict]:
    if not WATCH_PATH.exists():
        return []
    try:
        raw = json.loads(WATCH_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(raw, list) and raw and isinstance(raw[0], str):
        items = [{"symbol": normalize_symbol(s), "name": stock_name(s), "added_at": None} for s in raw]
        save_watchlist(items)
        return items
    out = []
    seen = set()
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        code = normalize_symbol(str(item.get("symbol") or ""))
        if not code.isdigit() or code in seen:
            continue
        seen.add(code)
        out.append(
            {
                "symbol": code,
                "name": item.get("name") or stock_name(code),
                "added_at": item.get("added_at"),
            }
        )
    return out


def save_watchlist(items: list[dict]) -> list[dict]:
    WATCH_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return items


def watch_symbols() -> set[str]:
    return {m["symbol"] for m in load_watchlist()}


def add_watch(symbol: str) -> dict:
    code = normalize_symbol(symbol)
    items = load_watchlist()
    if any(m["symbol"] == code for m in items):
        return {"ok": True, "added": False, "items": items}
    items.append(
        {
            "symbol": code,
            "name": stock_name(code),
            "added_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
    )
    save_watchlist(items)
    return {"ok": True, "added": True, "items": items}


def remove_watch(symbol: str) -> dict:
    code = normalize_symbol(symbol)
    items = [m for m in load_watchlist() if m["symbol"] != code]
    save_watchlist(items)
    return {"ok": True, "removed": True, "items": items}
