"""Pattern similarity: find stocks / windows whose shape matches a query segment."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from qt.data import load_bars, load_cached_bars, load_universe, stock_name


def zscore(arr: np.ndarray) -> np.ndarray:
    arr = np.asarray(arr, dtype=float)
    std = arr.std()
    if std < 1e-12:
        return arr - arr.mean()
    return (arr - arr.mean()) / std


def window_correlations(query: np.ndarray, series: np.ndarray) -> np.ndarray:
    """Pearson corr of `query` vs every sliding window in `series`. NaN if too short."""
    q = zscore(query)
    n = len(q)
    if len(series) < n:
        return np.array([])
    windows = sliding_window_view(np.asarray(series, dtype=float), n)
    means = windows.mean(axis=1)
    stds = windows.std(axis=1)
    stds = np.where(stds < 1e-12, np.nan, stds)
    normed = (windows - means[:, None]) / stds[:, None]
    return (normed * q).mean(axis=1)


@dataclass
class Match:
    symbol: str
    name: str
    start: str
    end: str
    corr: float
    forward_5: float | None
    forward_10: float | None
    query_norm: list[float]
    match_norm: list[float]
    match_close: list[float]
    dates: list[str]


def bars_for_match(symbol: str) -> pd.DataFrame:
    df = load_cached_bars(symbol)
    if df is not None and not df.empty:
        return df
    return load_bars(symbol, "20180101", None)


PRICE_W, VOL_W, TURN_W = 0.65, 0.25, 0.10


def query_frame(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    if df is None or df.empty:
        raise RuntimeError("没有行情")
    seg = df.loc[start:end]
    if seg.empty or "close" not in seg.columns:
        raise RuntimeError("所选区间没有收盘价")
    out = pd.DataFrame({"close": pd.to_numeric(seg["close"], errors="coerce")}).dropna()
    if len(out) < 8:
        raise RuntimeError("所选区间有效交易日不足 8 天，请拉长区间")
    for col in ("volume", "turnover"):
        if col in seg.columns:
            out[col] = pd.to_numeric(seg[col], errors="coerce").reindex(out.index)
    return out


def extract_segment(df: pd.DataFrame, start: str, end: str) -> pd.Series:
    return query_frame(df, start, end)["close"]


def _as_frame(query: pd.Series | pd.DataFrame, src: pd.DataFrame | None = None) -> pd.DataFrame:
    if isinstance(query, pd.DataFrame):
        return query
    frame = pd.DataFrame({"close": pd.to_numeric(query, errors="coerce")})
    if src is not None:
        for col in ("volume", "turnover"):
            if col in src.columns:
                frame[col] = pd.to_numeric(src[col], errors="coerce").reindex(query.index)
    return frame


def _corr_or_none(query_arr: np.ndarray, series: pd.Series | None, n: int) -> np.ndarray | None:
    if series is None or query_arr is None:
        return None
    q = np.asarray(query_arr, dtype=float)
    if len(q) != n or not np.isfinite(q).any() or np.nanstd(q) < 1e-12:
        return None
    s = pd.to_numeric(series, errors="coerce").fillna(0)
    if len(s) < n:
        return None
    out = window_correlations(np.nan_to_num(q, nan=0.0), s.values)
    return out if len(out) else None


def blend_window_scores(price: np.ndarray, volume: np.ndarray | None, turnover: np.ndarray | None) -> np.ndarray:
    score = np.zeros_like(price, dtype=float)
    wsum = np.zeros_like(price, dtype=float)
    ok = np.isfinite(price)
    score[ok] += PRICE_W * price[ok]
    wsum[ok] += PRICE_W
    if volume is not None and len(volume) == len(price):
        mv = ok & np.isfinite(volume)
        score[mv] += VOL_W * volume[mv]
        wsum[mv] += VOL_W
    if turnover is not None and len(turnover) == len(price):
        mt = ok & np.isfinite(turnover)
        score[mt] += TURN_W * turnover[mt]
        wsum[mt] += TURN_W
    blended = np.full_like(price, np.nan, dtype=float)
    mask = wsum > 0
    blended[mask] = score[mask] / wsum[mask]
    blended[~ok] = np.nan
    return blended


def window_flow_scores(
    query: pd.Series | pd.DataFrame,
    df: pd.DataFrame,
    lookback_days: int = 0,
    exclude_overlap: bool = False,
) -> dict:
    qf = _as_frame(query)
    close = df["close"].dropna()
    n = len(qf)
    if lookback_days and lookback_days > 0:
        keep = max(int(lookback_days), n)
        close = close.iloc[-keep:]
    price = window_correlations(qf["close"].values, close.values)
    if len(price) == 0:
        return {"index": close.index, "n": n, "price": price, "volume": None, "turnover": None, "score": price}
    if exclude_overlap:
        q0, q1 = qf.index[0], qf.index[-1]
        for i in range(len(price)):
            w0 = close.index[i]
            w1 = close.index[i + n - 1]
            if w0 <= q1 and w1 >= q0:
                price[i] = np.nan
    vol = _corr_or_none(qf["volume"].values if "volume" in qf.columns else None, df["volume"].reindex(close.index) if "volume" in df.columns else None, n)
    turn = _corr_or_none(qf["turnover"].values if "turnover" in qf.columns else None, df["turnover"].reindex(close.index) if "turnover" in df.columns else None, n)
    score = blend_window_scores(price, vol, turn)
    return {"index": close.index, "n": n, "price": price, "volume": vol, "turnover": turn, "score": score}


def _forward_return(close: pd.Series, end_ts, horizon: int) -> float | None:
    if end_ts not in close.index:
        loc = close.index.searchsorted(end_ts)
    else:
        loc = close.index.get_loc(end_ts)
        if isinstance(loc, slice):
            loc = loc.stop - 1
    loc = int(loc)
    j = loc + horizon
    if j >= len(close):
        return None
    a, b = float(close.iloc[loc]), float(close.iloc[j])
    if a == 0:
        return None
    return (b / a - 1) * 100


def _corr_at(arr: np.ndarray | None, i: int) -> float | None:
    if arr is None or i >= len(arr):
        return None
    v = arr[i]
    if not np.isfinite(v):
        return None
    return float(v)


def best_window(
    query: pd.Series | pd.DataFrame,
    df: pd.DataFrame,
    exclude_overlap: bool = False,
    lookback_days: int = 0,
) -> dict | None:
    flow = window_flow_scores(query, df, lookback_days=lookback_days, exclude_overlap=exclude_overlap)
    scores = flow["score"]
    if len(scores) == 0 or np.all(np.isnan(scores)):
        return None
    i = int(np.nanargmax(scores))
    n = flow["n"]
    close_s = df["close"].reindex(flow["index"]).dropna()
    if len(close_s) < i + n:
        return None
    window = close_s.iloc[i : i + n]
    if len(window) < n:
        return None
    fwd5 = _forward_return(close_s, window.index[-1], 5)
    fwd10 = _forward_return(close_s, window.index[-1], 10)
    return {
        "start": window.index[0].strftime("%Y-%m-%d"),
        "end": window.index[-1].strftime("%Y-%m-%d"),
        "corr": float(scores[i]),
        "corr_price": _corr_at(flow["price"], i),
        "corr_volume": _corr_at(flow["volume"], i),
        "corr_turnover": _corr_at(flow["turnover"], i),
        "forward_5": None if fwd5 is None else float(fwd5),
        "forward_10": None if fwd10 is None else float(fwd10),
        "match_norm": zscore(window.values).tolist(),
        "match_close": [float(x) for x in window.values],
        "dates": [d.strftime("%Y-%m-%d") for d in window.index],
    }


def frame_from_saved(item: dict) -> pd.DataFrame:
    closes = item.get("query_close") or []
    dates = item.get("query_dates") or []
    if len(closes) >= 8 and len(closes) == len(dates):
        idx = pd.to_datetime(dates)
        out = pd.DataFrame({"close": pd.to_numeric(closes, errors="coerce")}, index=idx)
        vols = item.get("query_volume") or []
        turns = item.get("query_turnover") or []
        if len(vols) == len(closes):
            out["volume"] = pd.to_numeric(vols, errors="coerce")
        if len(turns) == len(closes):
            out["turnover"] = pd.to_numeric(turns, errors="coerce")
        if ("volume" not in out.columns or "turnover" not in out.columns) and item.get("symbol"):
            try:
                src = bars_for_match(item["symbol"])
                qf = query_frame(src, item["start"], item["end"])
                for col in ("volume", "turnover"):
                    if col not in out.columns and col in qf.columns:
                        out[col] = qf[col].reindex(out.index)
            except Exception:
                pass
        return out
    src = bars_for_match(item["symbol"])
    return query_frame(src, item["start"], item["end"])


def series_from_saved(item: dict) -> pd.Series:
    return frame_from_saved(item)["close"]


def _list_or_none(frame: pd.DataFrame, col: str) -> list[float | None] | None:
    if col not in frame.columns:
        return None
    out: list[float | None] = []
    for x in frame[col].values:
        try:
            if x != x:
                out.append(None)
            else:
                out.append(float(x))
        except (TypeError, ValueError):
            out.append(None)
    return out


def _round_opt(v: float | None, n: int = 4) -> float | None:
    if v is None:
        return None
    return round(float(v), n)


METHOD = "price_volume_turnover"
METHOD_LABEL = "价+量+换手加权（0.65/0.25/0.10）z-score 皮尔逊相关"


def _scan_universe(
    query: pd.Series | pd.DataFrame,
    universe_key: str,
    exclude_symbol: str | None,
    lookback_days: int,
    include_self_history: bool,
) -> tuple[list[dict], int]:
    members = load_universe(universe_key)
    matches: list[dict] = []
    if include_self_history and exclude_symbol:
        try:
            src = bars_for_match(exclude_symbol)
            own = best_window(query, src, exclude_overlap=True, lookback_days=lookback_days)
        except Exception:
            own = None
        if own and own["corr"] >= 0.55:
            matches.append(
                {
                    "symbol": exclude_symbol,
                    "name": f"{stock_name(exclude_symbol)}（自身历史）",
                    **own,
                }
            )

    scanned = 0
    for m in members:
        code = m["symbol"]
        if exclude_symbol and code == exclude_symbol:
            continue
        scanned += 1
        try:
            df = bars_for_match(code)
        except Exception:
            continue
        qn = len(query) if not isinstance(query, pd.DataFrame) else len(query)
        if df is None or df.empty or len(df) < qn + 2:
            continue
        hit = best_window(query, df, exclude_overlap=False, lookback_days=lookback_days)
        if hit is None:
            continue
        matches.append({"symbol": code, "name": m.get("name") or stock_name(code), **hit})
    return matches, scanned


def find_similar(
    symbol: str,
    start: str,
    end: str,
    universe_key: str = "hs300",
    top_n: int = 8,
    include_self_history: bool = True,
    lookback_days: int = 0,
) -> dict:
    src = bars_for_match(symbol)
    query = query_frame(src, start, end)
    q_norm = zscore(query["close"].values).tolist()
    matches, scanned = _scan_universe(
        query,
        universe_key,
        exclude_symbol=symbol,
        lookback_days=lookback_days,
        include_self_history=include_self_history,
    )
    matches.sort(key=lambda x: x["corr"], reverse=True)
    top = matches[:top_n]
    for item in top:
        item["corr"] = round(item["corr"], 4)
        item["corr_price"] = _round_opt(item.get("corr_price"))
        item["corr_volume"] = _round_opt(item.get("corr_volume"))
        item["corr_turnover"] = _round_opt(item.get("corr_turnover"))
        if item["forward_5"] is not None:
            item["forward_5"] = round(item["forward_5"], 2)
        if item["forward_10"] is not None:
            item["forward_10"] = round(item["forward_10"], 2)
        item["query_norm"] = q_norm

    members = load_universe(universe_key)
    return {
        "symbol": symbol,
        "name": stock_name(symbol),
        "start": query.index[0].strftime("%Y-%m-%d"),
        "end": query.index[-1].strftime("%Y-%m-%d"),
        "window": len(query),
        "query_norm": q_norm,
        "query_dates": [d.strftime("%Y-%m-%d") for d in query.index],
        "query_close": [float(x) for x in query["close"].values],
        "query_volume": _list_or_none(query, "volume"),
        "query_turnover": _list_or_none(query, "turnover"),
        "lookback_days": lookback_days,
        "method": METHOD,
        "method_label": METHOD_LABEL,
        "matches": top,
        "scanned": scanned if scanned else len(members),
    }


def find_similar_many(
    queries: list[dict],
    universe_key: str = "low20",
    top_n: int = 12,
    lookback_days: int = 60,
    min_corr: float = 0.55,
) -> dict:
    """Match one or more templates. Each query dict needs symbol/start/end or stored series."""
    if not queries:
        raise RuntimeError("请至少选择一个形态（日期区间、框选或已保存模板）")
    packed = []
    for i, q in enumerate(queries):
        frame = frame_from_saved(q) if q.get("query_close") else None
        if frame is None:
            src = bars_for_match(q["symbol"])
            frame = query_frame(src, q["start"], q["end"])
        qid = q.get("id") or f"q{i}"
        packed.append(
            {
                "id": qid,
                "name": q.get("name") or f"{q.get('symbol')} {q.get('start')}~{q.get('end')}",
                "symbol": q.get("symbol"),
                "start": frame.index[0].strftime("%Y-%m-%d"),
                "end": frame.index[-1].strftime("%Y-%m-%d"),
                "window": len(frame),
                "query_norm": zscore(frame["close"].values).tolist(),
                "query_dates": [d.strftime("%Y-%m-%d") for d in frame.index],
                "query_close": [float(x) for x in frame["close"].values],
                "query_volume": _list_or_none(frame, "volume"),
                "query_turnover": _list_or_none(frame, "turnover"),
                "frame": frame,
            }
        )

    by_symbol: dict[str, dict] = {}
    scanned = 0
    for q in packed:
        hits, scanned = _scan_universe(
            q["frame"],
            universe_key,
            exclude_symbol=q.get("symbol"),
            lookback_days=lookback_days,
            include_self_history=False,
        )
        for hit in hits:
            if hit["corr"] < min_corr:
                continue
            rec = by_symbol.setdefault(
                hit["symbol"],
                {
                    "symbol": hit["symbol"],
                    "name": hit["name"],
                    "patterns": [],
                    "corr": -1.0,
                    "avg_corr": 0.0,
                },
            )
            rec["patterns"].append(
                {
                    "id": q["id"],
                    "name": q["name"],
                    "corr": round(hit["corr"], 4),
                    "corr_price": _round_opt(hit.get("corr_price")),
                    "corr_volume": _round_opt(hit.get("corr_volume")),
                    "corr_turnover": _round_opt(hit.get("corr_turnover")),
                    "start": hit["start"],
                    "end": hit["end"],
                    "forward_5": None if hit["forward_5"] is None else round(hit["forward_5"], 2),
                    "forward_10": None if hit["forward_10"] is None else round(hit["forward_10"], 2),
                    "match_norm": hit["match_norm"],
                }
            )
            if hit["corr"] > rec["corr"]:
                rec["corr"] = hit["corr"]
                rec["corr_price"] = hit.get("corr_price")
                rec["corr_volume"] = hit.get("corr_volume")
                rec["corr_turnover"] = hit.get("corr_turnover")
                rec["start"] = hit["start"]
                rec["end"] = hit["end"]
                rec["forward_5"] = hit["forward_5"]
                rec["forward_10"] = hit["forward_10"]
                rec["match_norm"] = hit["match_norm"]
                rec["query_norm"] = q["query_norm"]

    merged = []
    for rec in by_symbol.values():
        pats = rec["patterns"]
        rec["n_patterns"] = len(pats)
        rec["avg_corr"] = round(sum(p["corr"] for p in pats) / len(pats), 4)
        rec["corr"] = round(rec["corr"], 4)
        rec["corr_price"] = _round_opt(rec.get("corr_price"))
        rec["corr_volume"] = _round_opt(rec.get("corr_volume"))
        rec["corr_turnover"] = _round_opt(rec.get("corr_turnover"))
        if rec.get("forward_5") is not None:
            rec["forward_5"] = round(rec["forward_5"], 2)
        if rec.get("forward_10") is not None:
            rec["forward_10"] = round(rec["forward_10"], 2)
        merged.append(rec)

    merged.sort(key=lambda x: (x["n_patterns"], x["corr"], x["avg_corr"]), reverse=True)
    top = merged[:top_n]
    queries_out = [{k: v for k, v in q.items() if k != "frame"} for q in packed]
    return {
        "queries": queries_out,
        "lookback_days": lookback_days,
        "method": METHOD,
        "method_label": METHOD_LABEL,
        "matches": top,
        "scanned": scanned,
        "query_norm": queries_out[0]["query_norm"] if queries_out else [],
        "window": queries_out[0]["window"] if queries_out else 0,
        "symbol": queries_out[0].get("symbol") if queries_out else None,
        "name": queries_out[0].get("name") if queries_out else None,
        "start": queries_out[0].get("start") if queries_out else None,
        "end": queries_out[0].get("end") if queries_out else None,
    }
