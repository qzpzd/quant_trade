"""Per-stock opening (09:15-09:25) and closing (14:57-15:00) call-auction analysis."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pandas as pd
import requests

from qt.config import AUCTION_DIR
from qt.data import load_bars, load_cached_bars, normalize_symbol, stock_name

OPEN_START, OPEN_END = "09:15", "09:25"
CLOSE_START, CLOSE_END = "14:57", "15:00"
CONT_END = "14:56"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Referer": "https://quote.eastmoney.com/",
    "Accept": "application/json, text/plain, */*",
}


def _secid(symbol: str) -> str:
    code = normalize_symbol(symbol)
    market = 1 if code.startswith("6") else 0
    return f"{market}.{code}"


def _hm(ts) -> str:
    t = pd.Timestamp(ts)
    return t.strftime("%H:%M")


def _in_range(ts, start: str, end: str) -> bool:
    hm = _hm(ts)
    return start <= hm <= end


def classify_gap(pct: float | None) -> str:
    if pct is None:
        return "—"
    if pct >= 2:
        return "大幅高开"
    if pct >= 0.5:
        return "高开"
    if pct > -0.5:
        return "平开"
    if pct > -2:
        return "低开"
    return "大幅低开"


def classify_close_move(pct: float | None) -> str:
    if pct is None:
        return "—"
    if pct >= 0.5:
        return "尾盘拉升"
    if pct <= -0.5:
        return "尾盘回落"
    return "尾盘平稳"


def _round(v, n=3):
    if v is None:
        return None
    try:
        return round(float(v), n)
    except (TypeError, ValueError):
        return None


def _pct(a, b) -> float | None:
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return None
    if b == 0:
        return None
    return (a / b - 1) * 100


def _sum(series) -> float:
    if series is None:
        return 0.0
    return float(pd.to_numeric(series, errors="coerce").fillna(0).sum())


def _path(df: pd.DataFrame) -> list[dict]:
    out = []
    for ts, row in df.iterrows():
        price = row.get("close")
        if price is None or (isinstance(price, float) and pd.isna(price)):
            price = row.get("open")
        out.append(
            {
                "time": pd.Timestamp(ts).strftime("%H:%M"),
                "price": _round(price, 3),
                "volume": _round(row.get("volume"), 0),
                "amount": _round(row.get("amount"), 0),
            }
        )
    return out


def parse_trends(rows: list[str]) -> pd.DataFrame:
    records = []
    for item in rows or []:
        parts = str(item).split(",")
        if len(parts) < 7:
            continue
        records.append(
            {
                "time": parts[0],
                "open": parts[1],
                "close": parts[2],
                "high": parts[3],
                "low": parts[4],
                "volume": parts[5],
                "amount": parts[6],
            }
        )
    if not records:
        return pd.DataFrame(columns=["open", "close", "high", "low", "volume", "amount"])
    df = pd.DataFrame(records)
    df["time"] = pd.to_datetime(df["time"])
    for col in ("open", "close", "high", "low", "volume", "amount"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.set_index("time").sort_index()


def _tencent_code(symbol: str) -> str:
    code = normalize_symbol(symbol)
    if code.startswith("6"):
        return f"sh{code}"
    if code.startswith(("4", "8", "9")):
        return f"bj{code}"
    return f"sz{code}"


def parse_tencent_m1(rows: list) -> pd.DataFrame:
    records = []
    for row in rows or []:
        if not row or len(row) < 6:
            continue
        ts = str(row[0])
        if len(ts) < 12:
            continue
        records.append(
            {
                "time": datetime.strptime(ts[:12], "%Y%m%d%H%M"),
                "open": row[1],
                "close": row[2],
                "high": row[3],
                "low": row[4],
                "volume": row[5],
                "amount": None,
            }
        )
    if not records:
        return pd.DataFrame(columns=["open", "close", "high", "low", "volume", "amount"])
    df = pd.DataFrame(records).set_index("time").sort_index()
    for col in ("open", "close", "high", "low", "volume", "amount"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def fetch_tencent_minutes(symbol: str, ndays: int = 5) -> pd.DataFrame:
    """Tencent 1-min includes 14:57-15:00 closing auction; 09:15-09:25 is usually absent."""
    count = max(int(ndays) * 250, 800)
    url = "https://ifzq.gtimg.cn/appstock/app/kline/mkline"
    params = {"param": f"{_tencent_code(symbol)},m1,,{count}"}
    r = requests.get(url, params=params, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=15)
    r.raise_for_status()
    payload = ((r.json() or {}).get("data") or {}).get(_tencent_code(symbol)) or {}
    return parse_tencent_m1(payload.get("m1") or [])


def fetch_eastmoney_minutes(symbol: str, ndays: int = 5) -> pd.DataFrame:
    params = {
        "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "ndays": str(ndays),
        "iscr": "1",
        "iscca": "1",
        "secid": _secid(symbol),
    }
    last_err = None
    for host in (
        "https://push2his.eastmoney.com/api/qt/stock/trends2/get",
        "https://82.push2his.eastmoney.com/api/qt/stock/trends2/get",
    ):
        try:
            r = requests.get(host, params=params, headers=HEADERS, timeout=8)
            r.raise_for_status()
            trends = ((r.json() or {}).get("data") or {}).get("trends") or []
            df = parse_trends(trends)
            if not df.empty:
                return df
        except Exception as exc:
            last_err = exc
    if last_err:
        raise last_err
    return pd.DataFrame(columns=["open", "close", "high", "low", "volume", "amount"])


def parse_sina_minutes(text: str) -> pd.DataFrame:
    start = text.find("[")
    end = text.rfind("]")
    if start < 0 or end < 0:
        return pd.DataFrame(columns=["open", "close", "high", "low", "volume", "amount"])
    rows = json.loads(text[start : end + 1])
    records = []
    for row in rows or []:
        ts = row.get("day") or row.get("time")
        if not ts:
            continue
        records.append(
            {
                "time": pd.to_datetime(ts),
                "open": row.get("open"),
                "close": row.get("close"),
                "high": row.get("high"),
                "low": row.get("low"),
                "volume": row.get("volume"),
                "amount": row.get("amount"),
            }
        )
    if not records:
        return pd.DataFrame(columns=["open", "close", "high", "low", "volume", "amount"])
    df = pd.DataFrame(records).set_index("time").sort_index()
    for col in ("open", "close", "high", "low", "volume", "amount"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def fetch_sina_minutes(symbol: str, ndays: int = 5) -> pd.DataFrame:
    """Sina 1-min includes 14:57 and 15:00 with real volume/amount; 09:15-09:25 is usually absent."""
    url = "https://quotes.sina.cn/cn/api/jsonp_v2.php/x/CN_MarketDataService.getKLineData"
    params = {
        "symbol": _tencent_code(symbol),
        "scale": "1",
        "ma": "no",
        "datalen": str(max(int(ndays) * 250, 800)),
    }
    headers = {
        "User-Agent": HEADERS["User-Agent"],
        "Referer": "https://finance.sina.com.cn/",
    }
    r = requests.get(url, params=params, headers=headers, timeout=15)
    r.raise_for_status()
    return parse_sina_minutes(r.text)


def fetch_minute_trends(symbol: str, ndays: int = 5) -> pd.DataFrame:
    """1-min bars. Closing auction 14:57-15:00 is included; 09:15-09:25 when the feed sends it."""
    last_err = None
    for loader in (fetch_eastmoney_minutes, fetch_sina_minutes, fetch_tencent_minutes):
        try:
            df = loader(symbol, ndays=ndays)
            if not df.empty:
                return df
        except Exception as exc:
            last_err = exc
    if last_err:
        raise RuntimeError(f"竞价分钟线获取失败: {last_err}")
    return pd.DataFrame(columns=["open", "close", "high", "low", "volume", "amount"])


def load_minute_trends(symbol: str, ndays: int = 5, refresh: bool = False) -> pd.DataFrame:
    code = normalize_symbol(symbol)
    path = AUCTION_DIR / f"{code}.pkl"
    if path.exists() and not refresh:
        cached = pd.read_pickle(path)
        cached.index = pd.to_datetime(cached.index)
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        if datetime.now() - mtime < timedelta(minutes=15) and len(cached) >= 400:
            return cached
    try:
        fresh = fetch_minute_trends(code, ndays=ndays)
        if not fresh.empty:
            fresh.to_pickle(path)
            return fresh
        if path.exists():
            cached = pd.read_pickle(path)
            cached.index = pd.to_datetime(cached.index)
            return cached
        return fresh
    except Exception:
        if path.exists():
            cached = pd.read_pickle(path)
            cached.index = pd.to_datetime(cached.index)
            return cached
        raise


def session_from_minutes(day: pd.DataFrame, pre_close: float | None, daily_open: float | None = None) -> dict:
    if day is None or day.empty:
        return {}
    open_bars = day[_in_range_index(day, OPEN_START, OPEN_END)]
    close_bars = day[_in_range_index(day, CLOSE_START, CLOSE_END)]
    first_cont = day[_in_range_index(day, "09:30", "09:30")]
    cont_last = day[_in_range_index(day, CONT_END, CONT_END)]
    if cont_last.empty:
        before = day[day.index.map(lambda t: _hm(t) < CLOSE_START)]
        cont_last = before.iloc[-1:] if not before.empty else day.iloc[0:0]

    date = pd.Timestamp(day.index[0]).strftime("%Y-%m-%d")
    open_source = "分钟竞价"
    if open_bars.empty:
        open_source = "日线开盘价（竞价结果）"
        price = daily_open
        if price is None and not first_cont.empty:
            price = float(first_cont["close"].iloc[0])
        open_vol = _sum(first_cont["volume"]) if not first_cont.empty else None
        open_amt = _sum(first_cont["amount"]) if not first_cont.empty else None
        open_path = _path(first_cont) if not first_cont.empty else []
        open_high = price
        open_low = price
    else:
        last = open_bars.iloc[-1]
        price = float(last["close"] if pd.notna(last["close"]) else last["open"])
        open_vol = _sum(open_bars["volume"])
        open_amt = _sum(open_bars["amount"])
        open_path = _path(open_bars)
        open_high = float(open_bars["high"].max())
        open_low = float(open_bars["low"].min())

    gap = _pct(price, pre_close) if price is not None else None
    close_price = None
    close_vol = close_amt = close_vs_cont = None
    close_path = []
    cont_price = None
    if not close_bars.empty:
        last_c = close_bars.iloc[-1]
        close_price = float(last_c["close"] if pd.notna(last_c["close"]) else last_c["open"])
        close_vol = _sum(close_bars["volume"])
        close_amt = _sum(close_bars["amount"])
        close_path = _path(close_bars)
        if not cont_last.empty:
            cont_price = float(cont_last["close"].iloc[-1])
            close_vs_cont = _pct(close_price, cont_price)

    return {
        "date": date,
        "pre_close": _round(pre_close, 3),
        "open_price": _round(price, 3),
        "open_gap_pct": _round(gap, 2),
        "open_bias": classify_gap(gap),
        "open_volume": _round(open_vol, 0),
        "open_amount": _round(open_amt, 0),
        "open_high": _round(open_high, 3),
        "open_low": _round(open_low, 3),
        "open_path": open_path,
        "open_source": open_source,
        "cont_price": _round(cont_price, 3),
        "close_price": _round(close_price, 3),
        "close_vs_cont_pct": _round(close_vs_cont, 2),
        "close_bias": classify_close_move(close_vs_cont),
        "close_volume": _round(close_vol, 0),
        "close_amount": _round(close_amt, 0),
        "close_path": close_path,
        "close_vs_open_pct": _round(_pct(close_price, price), 2) if close_price is not None else None,
    }


def _in_range_index(df: pd.DataFrame, start: str, end: str) -> pd.Series:
    return pd.Series([_in_range(t, start, end) for t in df.index], index=df.index)


def history_from_daily(daily: pd.DataFrame, lookback: int = 60) -> dict:
    if daily is None or daily.empty or len(daily) < 3:
        return {}
    df = daily.iloc[-lookback:].copy()
    prev = df["close"].shift(1)
    gap = (df["open"] / prev - 1) * 100
    close_vs_open = (df["close"] / df["open"] - 1) * 100
    close_vs_prev = (df["close"] / prev - 1) * 100
    g = gap.dropna()
    up = g >= 0.5
    down = g <= -0.5
    n = int(len(g))
    return {
        "days": n,
        "avg_gap_pct": _round(float(g.mean()), 2) if n else None,
        "gap_up": int(up.sum()),
        "gap_down": int(down.sum()),
        "gap_flat": int((~up & ~down).sum()),
        "gap_up_then_up": int(((close_vs_open >= 0) & up).sum()),
        "gap_up_then_red": int(((close_vs_prev > 0) & up).sum()),
        "gap_down_then_down": int(((close_vs_open <= 0) & down).sum()),
        "close_up_vs_open": int((close_vs_open > 0).sum()),
    }


def _why_open(s: dict) -> str:
    bits = []
    bits.append(s.get("open_bias") or "—")
    if s.get("open_gap_pct") is not None:
        bits.append(f"相对昨收 {s['open_gap_pct']:+.2f}%")
    src = s.get("open_source") or ""
    if "日线" in src:
        bits.append("分钟线未给出 09:15-09:25，开盘价即早盘竞价成交价")
    elif s.get("open_path"):
        bits.append(f"竞价 {len(s['open_path'])} 根分钟")
    if s.get("open_amount") and "分钟竞价" in (s.get("open_source") or ""):
        bits.append(f"竞价额 {s['open_amount']:.0f}")
    return "；".join(bits)


def _why_close(s: dict) -> str:
    bits = []
    bits.append(s.get("close_bias") or "—")
    if s.get("close_vs_cont_pct") is not None:
        bits.append(f"相对 14:56 {s['close_vs_cont_pct']:+.2f}%")
    elif s.get("close_price") is None:
        bits.append("还没有尾盘分钟（交易中或数据未到）")
    if s.get("close_vs_open_pct") is not None:
        bits.append(f"相对开盘 {s['close_vs_open_pct']:+.2f}%")
    if s.get("close_amount"):
        bits.append(f"尾盘额 {s['close_amount']:.0f}")
    return "；".join(bits)


def analyze_auction(symbol: str, lookback: int = 60) -> dict:
    code = normalize_symbol(symbol)
    daily = load_cached_bars(code)
    if daily is None or daily.empty:
        daily = load_bars(code, "20220101", None)
    if daily is None or daily.empty:
        raise RuntimeError(f"没有 {code} 的日线，无法对照昨收")

    minutes = pd.DataFrame()
    minute_error = None
    try:
        minutes = load_minute_trends(code, ndays=5)
    except Exception as exc:
        minute_error = str(exc)

    sessions = []
    if not minutes.empty:
        for day, grp in minutes.groupby(minutes.index.normalize()):
            day_ts = pd.Timestamp(day).normalize()
            prev_rows = daily[daily.index.normalize() < day_ts]
            prev = float(prev_rows["close"].iloc[-1]) if not prev_rows.empty else None
            same = daily[daily.index.normalize() == day_ts]
            daily_open = float(same["open"].iloc[0]) if not same.empty else None
            rec = session_from_minutes(grp, prev, daily_open)
            if rec:
                sessions.append(rec)

    last_daily = daily.iloc[-1]
    last_date = daily.index[-1].strftime("%Y-%m-%d")
    last_prev = float(daily["close"].iloc[-2]) if len(daily) > 1 else None
    latest = sessions[-1] if sessions else {
        "date": last_date,
        "pre_close": _round(last_prev, 3),
        "open_price": _round(last_daily["open"], 3),
        "open_gap_pct": _round(_pct(last_daily["open"], last_prev), 2),
        "open_bias": classify_gap(_pct(last_daily["open"], last_prev)),
        "open_volume": None,
        "open_amount": None,
        "open_path": [],
        "open_source": "日线开盘价（竞价结果）",
        "close_price": _round(last_daily["close"], 3),
        "close_vs_open_pct": _round(_pct(last_daily["close"], last_daily["open"]), 2),
        "close_vs_cont_pct": None,
        "close_bias": classify_close_move(_pct(last_daily["close"], last_daily["open"])),
        "close_volume": None,
        "close_amount": None,
        "close_path": [],
        "cont_price": None,
    }

    hist = history_from_daily(daily, lookback=lookback)
    opening = {
        "session": "早盘集合竞价 09:15–09:25",
        "date": latest.get("date"),
        "price": latest.get("open_price"),
        "pre_close": latest.get("pre_close"),
        "gap_pct": latest.get("open_gap_pct"),
        "bias": latest.get("open_bias"),
        "volume": latest.get("open_volume"),
        "amount": latest.get("open_amount"),
        "high": latest.get("open_high"),
        "low": latest.get("open_low"),
        "path": latest.get("open_path") or [],
        "source": latest.get("open_source"),
        "why": _why_open(latest),
    }
    closing = {
        "session": "尾盘集合竞价 14:57–15:00",
        "date": latest.get("date"),
        "price": latest.get("close_price"),
        "cont_price": latest.get("cont_price"),
        "auc_pct": latest.get("close_vs_cont_pct"),
        "vs_open_pct": latest.get("close_vs_open_pct"),
        "bias": latest.get("close_bias"),
        "volume": latest.get("close_volume"),
        "amount": latest.get("close_amount"),
        "path": latest.get("close_path") or [],
        "why": _why_close(latest),
    }
    notes = [
        "A 股开盘价即早盘集合竞价成交价；2018-08-20 起收盘价即尾盘集合竞价成交价。",
        "尾盘路径来自 1 分钟线 14:57–15:00（东财优先，其次新浪/腾讯，最近约 5 个交易日）。",
        "早盘 09:15–09:25 虚拟匹配若接口未返回，则用开盘价作为竞价结果，开盘第一分钟量作量能参考。",
        "研究用途，不构成投资建议。",
    ]
    if minute_error:
        notes.insert(0, f"分钟线暂不可用：{minute_error}。已改用日线开收盘作为竞价结果。")

    return {
        "symbol": code,
        "name": stock_name(code),
        "opening": opening,
        "closing": closing,
        "sessions": sessions[-12:],
        "history": hist,
        "notes": notes,
    }
