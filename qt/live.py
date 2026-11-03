"""准实时行情：个股/自选现价（东财推送）+ 分钟线短缓存。"""

from __future__ import annotations

import threading
import time
from datetime import datetime, time as dtime
from typing import Any

import pandas as pd
import requests

from qt.auction import load_minute_trends
from qt.data import normalize_symbol, stock_name
from qt.watchlist import load_watchlist

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Referer": "https://quote.eastmoney.com/",
}

# 内存短缓存：全市场 spot 太重，这里只缓存「最近一次按代码批量查询」
_lock = threading.Lock()
_quote_cache: dict[str, Any] = {"at": 0.0, "by_symbol": {}}
QUOTE_TTL_SEC = 8.0
MINUTE_TTL_SEC = 60.0

_minute_meta: dict[str, float] = {}


def _secid(symbol: str) -> str:
    code = normalize_symbol(symbol)
    market = 1 if code.startswith(("6", "5", "9")) else 0
    return f"{market}.{code}"


def market_session(now: datetime | None = None) -> dict[str, Any]:
    """A 股交易时段判断（不含节假日休市表，仅工作日+时钟）。"""
    now = now or datetime.now()
    weekday = now.weekday()  # 0=Mon
    hm = now.time()
    is_weekday = weekday < 5
    morning = dtime(9, 15) <= hm <= dtime(11, 30)
    afternoon = dtime(13, 0) <= hm <= dtime(15, 5)
    in_session = bool(is_weekday and (morning or afternoon))
    # 盘前准备 / 盘后缓冲也可稍勤刷新
    near_session = bool(
        is_weekday
        and (dtime(9, 0) <= hm <= dtime(11, 35) or dtime(12, 55) <= hm <= dtime(15, 15))
    )
    if in_session:
        poll_sec = 8
        label = "交易中"
    elif near_session:
        poll_sec = 20
        label = "临近开盘/收盘"
    elif is_weekday and hm < dtime(9, 0):
        poll_sec = 60
        label = "盘前"
    elif is_weekday and hm > dtime(15, 5):
        poll_sec = 120
        label = "已收盘"
    else:
        poll_sec = 180
        label = "休市"
    return {
        "now": now.strftime("%Y-%m-%d %H:%M:%S"),
        "weekday": weekday,
        "in_session": in_session,
        "near_session": near_session,
        "label": label,
        "poll_sec": poll_sec,
        "quote_ttl_sec": QUOTE_TTL_SEC,
        "minute_ttl_sec": MINUTE_TTL_SEC,
    }


def _fetch_em_quotes(symbols: list[str]) -> dict[str, dict[str, Any]]:
    codes = [normalize_symbol(s) for s in symbols if normalize_symbol(s).isdigit()]
    codes = list(dict.fromkeys(codes))
    if not codes:
        return {}
    out: dict[str, dict[str, Any]] = {}
    # 东财 ulist 一次不宜过多
    for i in range(0, len(codes), 80):
        chunk = codes[i : i + 80]
        secids = ",".join(_secid(c) for c in chunk)
        url = "https://push2.eastmoney.com/api/qt/ulist.np/get"
        params = {
            "fltt": "2",
            "invt": "2",
            "fields": "f12,f14,f2,f3,f4,f5,f6,f8,f15,f16,f17,f18,f9",
            "secids": secids,
            "pn": "1",
            "pz": str(len(chunk)),
        }
        r = requests.get(url, params=params, headers=HEADERS, timeout=8)
        r.raise_for_status()
        data = r.json() or {}
        diff = ((data.get("data") or {}).get("diff")) or []
        if isinstance(diff, dict):
            diff = list(diff.values())
        for row in diff:
            if not isinstance(row, dict):
                continue
            code = normalize_symbol(str(row.get("f12") or ""))
            if not code:
                continue

            def _num(key: str) -> float | None:
                v = row.get(key)
                if v is None or v == "-" or v == "":
                    return None
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return None

            price = _num("f2")
            pre = _num("f18")
            pct = _num("f3")
            if pct is None and price is not None and pre:
                pct = (price / pre - 1.0) * 100.0
            out[code] = {
                "symbol": code,
                "name": str(row.get("f14") or "") or stock_name(code),
                "price": price,
                "pct_chg": round(pct, 2) if pct is not None else None,
                "chg": _num("f4"),
                "volume": _num("f5"),
                "amount": _num("f6"),
                "turnover": _num("f8"),
                "high": _num("f15"),
                "low": _num("f16"),
                "open": _num("f17"),
                "pre_close": pre,
                "pe": _num("f9"),
                "source": "eastmoney",
            }
    return out


def get_quotes(symbols: list[str], force: bool = False) -> dict[str, Any]:
    """按代码取准实时现价；短 TTL 内存缓存，避免狂刷东财。"""
    codes = [normalize_symbol(s) for s in symbols if normalize_symbol(s).isdigit()]
    codes = list(dict.fromkeys(codes))
    session = market_session()
    now = time.time()
    with _lock:
        cached: dict[str, dict] = dict(_quote_cache.get("by_symbol") or {})
        at = float(_quote_cache.get("at") or 0)
        age = now - at
        need = [c for c in codes if c not in cached] if not force else list(codes)
        if not force and age < QUOTE_TTL_SEC:
            need = [c for c in need if c not in cached]
        else:
            # TTL 过期：刷新请求列表中的全部
            need = list(codes)

    fresh: dict[str, dict] = {}
    err = None
    if need:
        try:
            fresh = _fetch_em_quotes(need)
        except Exception as exc:
            err = str(exc)
            fresh = {}

    with _lock:
        by = dict(_quote_cache.get("by_symbol") or {})
        if fresh:
            by.update(fresh)
            _quote_cache["by_symbol"] = by
            _quote_cache["at"] = time.time()
        else:
            by = dict(_quote_cache.get("by_symbol") or {})
        items = []
        for c in codes:
            q = by.get(c)
            if q:
                items.append(q)
            else:
                items.append(
                    {
                        "symbol": c,
                        "name": stock_name(c),
                        "price": None,
                        "pct_chg": None,
                        "missing": True,
                    }
                )
        return {
            "ok": True,
            "session": session,
            "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "ttl_sec": QUOTE_TTL_SEC,
            "count": len(items),
            "items": items,
            "error": err,
        }


def get_watchlist_quotes(force: bool = False) -> dict[str, Any]:
    symbols = [m["symbol"] for m in load_watchlist()]
    payload = get_quotes(symbols, force=force)
    payload["scope"] = "watchlist"
    return payload


def get_live_quote(symbol: str, force: bool = False) -> dict[str, Any]:
    code = normalize_symbol(symbol)
    pack = get_quotes([code], force=force)
    item = (pack.get("items") or [{}])[0]
    return {
        "ok": True,
        "session": pack.get("session"),
        "as_of": pack.get("as_of"),
        "ttl_sec": pack.get("ttl_sec"),
        "error": pack.get("error"),
        **item,
    }


def get_live_minutes(symbol: str, ndays: int = 1, force: bool = False) -> dict[str, Any]:
    code = normalize_symbol(symbol)
    session = market_session()
    now = time.time()
    last = _minute_meta.get(code, 0.0)
    age = now - last
    if force or last <= 0:
        refresh = True
    elif session.get("in_session") or session.get("near_session"):
        refresh = age >= MINUTE_TTL_SEC
    else:
        refresh = age >= 600

    df = load_minute_trends(code, ndays=max(1, min(ndays, 5)), refresh=refresh)
    if refresh or code not in _minute_meta:
        _minute_meta[code] = time.time()

    bars = []
    if df is not None and not df.empty:
        for ts, row in df.iterrows():
            bars.append(
                {
                    "time": pd.Timestamp(ts).strftime("%Y-%m-%d %H:%M"),
                    "open": float(row["open"]) if pd.notna(row.get("open")) else None,
                    "high": float(row["high"]) if pd.notna(row.get("high")) else None,
                    "low": float(row["low"]) if pd.notna(row.get("low")) else None,
                    "close": float(row["close"]) if pd.notna(row.get("close")) else None,
                    "volume": float(row["volume"]) if pd.notna(row.get("volume")) else None,
                    "amount": float(row["amount"]) if "amount" in row and pd.notna(row.get("amount")) else None,
                }
            )
    last_bar = bars[-1] if bars else None
    return {
        "ok": True,
        "symbol": code,
        "name": stock_name(code),
        "session": session,
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "refreshed": refresh,
        "n": len(bars),
        "last": last_bar,
        "bars": bars,
    }


def live_status() -> dict[str, Any]:
    session = market_session()
    with _lock:
        at = float(_quote_cache.get("at") or 0)
        n = len(_quote_cache.get("by_symbol") or {})
    return {
        "ok": True,
        "session": session,
        "quote_cache_n": n,
        "quote_cache_age_sec": round(time.time() - at, 1) if at else None,
        "hint": (
            f"盘中约每 {session['poll_sec']} 秒刷新自选现价；"
            f"分钟线约 {MINUTE_TTL_SEC:.0f} 秒；日线仍靠收盘后/手动同步。"
        ),
    }
