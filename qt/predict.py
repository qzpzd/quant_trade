"""Short-horizon path forecast: cache-wide analog windows + trend slope."""

from __future__ import annotations

import numpy as np
import pandas as pd

from qt.data import list_cached_symbols, load_bars, load_cached_bars, stock_name
from qt.indicators import enrich, last_snapshot
from qt.similarity import window_flow_scores
from qt.signals import current_view

MIN_ANALOG_SCORE = 0.35
OWN_GAP_DAYS = 10


def _linreg_path(close: pd.Series, horizon: int) -> list[float]:
    y = np.log(close.iloc[-60:].values.astype(float))
    x = np.arange(len(y))
    slope, _intercept = np.polyfit(x, y, 1)
    last = float(close.iloc[-1])
    daily = float(np.exp(slope) - 1)
    return [last * ((1 + daily) ** (i + 1)) for i in range(horizon)]


def _query_frame(df: pd.DataFrame, lookback: int) -> pd.DataFrame:
    close = df["close"].dropna()
    cols = [c for c in ("close", "volume", "turnover") if c in df.columns]
    return df.loc[close.index[-lookback:], cols].copy()


def _collect_paths_from_flow(
    flow: dict,
    close: pd.Series,
    lookback: int,
    horizon: int,
    *,
    top_k: int,
    min_score: float,
    gap: int,
    symbol: str,
    name: str,
) -> list[dict]:
    scores = np.array(flow["score"], dtype=float, copy=True)
    n = lookback
    if len(scores) == 0 or np.all(np.isnan(scores)):
        return []
    ranked = np.argsort(np.nan_to_num(scores, nan=-2))[::-1]
    out: list[dict] = []
    used: list[int] = []
    for idx in ranked:
        if len(out) >= top_k:
            break
        if not np.isfinite(scores[idx]) or scores[idx] < min_score:
            break
        if gap and any(abs(idx - u) < gap for u in used):
            continue
        end_loc = idx + n - 1
        fut_end = end_loc + horizon
        if fut_end >= len(close):
            continue
        future = close.iloc[end_loc : fut_end + 1].values.astype(float)
        if future[0] == 0:
            continue
        rel = future / future[0]
        start_ts = close.index[idx]
        end_ts = close.index[end_loc]
        out.append(
            {
                "symbol": symbol,
                "name": name,
                "score": float(scores[idx]),
                "start": pd.Timestamp(start_ts).strftime("%Y-%m-%d"),
                "end": pd.Timestamp(end_ts).strftime("%Y-%m-%d"),
                "rel": rel,
            }
        )
        used.append(idx)
    return out


def analog_paths_cache(
    symbol: str,
    df: pd.DataFrame,
    lookback: int,
    horizon: int,
    *,
    top_k: int = 40,
    min_score: float = MIN_ANALOG_SCORE,
    per_stock: int = 2,
) -> dict:
    """Match lookback window (price+volume+turnover) across all cached bars."""
    close = df["close"].dropna()
    if len(close) < lookback + horizon + 5:
        raise RuntimeError("历史长度不足，无法做形态类比预测")
    query = _query_frame(df, lookback)
    hits: list[dict] = []

    # 本股自身历史（exclude_overlap 避开与当前查询窗重叠）
    try:
        flow_own = window_flow_scores(query, df, lookback_days=0, exclude_overlap=True)
        hits.extend(
            _collect_paths_from_flow(
                flow_own,
                close,
                lookback,
                horizon,
                top_k=max(6, per_stock * 4),
                min_score=min_score,
                gap=OWN_GAP_DAYS,
                symbol=symbol,
                name=f"{stock_name(symbol)}（自身历史）",
            )
        )
    except Exception:
        pass

    scanned = 0
    for code in list_cached_symbols():
        if code == symbol:
            continue
        scanned += 1
        other = load_cached_bars(code)
        if other is None or other.empty or len(other) < lookback + horizon + 5:
            continue
        try:
            flow = window_flow_scores(query, other, lookback_days=0, exclude_overlap=False)
            hits.extend(
                _collect_paths_from_flow(
                    flow,
                    other["close"].dropna(),
                    lookback,
                    horizon,
                    top_k=per_stock,
                    min_score=min_score,
                    gap=OWN_GAP_DAYS,
                    symbol=code,
                    name=stock_name(code),
                )
            )
        except Exception:
            continue

    if not hits:
        raise RuntimeError("缓存中相似窗口过少，无法做类比预测（可先同步更多股票日线）")

    hits.sort(key=lambda h: h["score"], reverse=True)
    selected = hits[:top_k]
    mat = np.vstack([h["rel"] for h in selected])
    p50 = np.median(mat, axis=0)
    p25 = np.percentile(mat, 25, axis=0)
    p75 = np.percentile(mat, 75, axis=0)
    last = float(close.iloc[-1])
    sources = [
        {
            "symbol": h["symbol"],
            "name": h["name"],
            "score": round(h["score"], 4),
            "start": h["start"],
            "end": h["end"],
        }
        for h in selected[:12]
    ]
    return {
        "n_analogs": int(mat.shape[0]),
        "scanned": scanned,
        "sources": sources,
        "median": (p50 * last).tolist(),
        "low": (p25 * last).tolist(),
        "high": (p75 * last).tolist(),
        "median_return_pct": round(float(p50[-1] - 1) * 100, 2),
        "p25_return_pct": round(float(p25[-1] - 1) * 100, 2),
        "p75_return_pct": round(float(p75[-1] - 1) * 100, 2),
    }


def forecast(symbol: str, lookback: int = 30, horizon: int = 10) -> dict:
    df = load_bars(symbol, "20180101", None)
    if df.empty:
        raise RuntimeError("没有行情")
    x = enrich(df)
    snap = last_snapshot(x)
    view = current_view(df)
    analog = analog_paths_cache(symbol, df, lookback=lookback, horizon=horizon)
    trend = _linreg_path(df["close"], horizon)

    last_close = float(df["close"].iloc[-1])
    last_date = pd.Timestamp(df.index[-1])
    future_dates = pd.bdate_range(last_date + pd.Timedelta(days=1), periods=horizon).strftime("%Y-%m-%d").tolist()

    adx_v = snap.get("adx14") or 15
    w_trend = min(max((adx_v - 15) / 25, 0), 0.65)
    w_analog = 1 - w_trend
    # analog["median"] 含 t0（当前价）
    analog_fwd = analog["median"][1:] if len(analog["median"]) == horizon + 1 else analog["median"][:horizon]
    analog_low = analog["low"][1:] if len(analog["low"]) == horizon + 1 else analog["low"][:horizon]
    analog_high = analog["high"][1:] if len(analog["high"]) == horizon + 1 else analog["high"][:horizon]
    if len(analog_fwd) < horizon:
        analog_fwd = analog["median"][-horizon:]
        analog_low = analog["low"][-horizon:]
        analog_high = analog["high"][-horizon:]

    blended = [w_analog * analog_fwd[i] + w_trend * trend[i] for i in range(horizon)]

    blended_ret = (blended[-1] / last_close - 1) * 100
    if blended_ret > 3:
        bias = "偏上涨"
    elif blended_ret < -3:
        bias = "偏下跌"
    else:
        bias = "震荡"

    hist_tail = df.iloc[-80:]
    history = []
    for d, row in hist_tail.iterrows():
        item = {"date": d.strftime("%Y-%m-%d"), "close": float(row["close"])}
        if "volume" in hist_tail.columns and row["volume"] == row["volume"]:
            item["volume"] = float(row["volume"])
        if "turnover" in hist_tail.columns and row["turnover"] == row["turnover"]:
            item["turnover"] = float(row["turnover"])
        history.append(item)

    return {
        "symbol": symbol,
        "name": stock_name(symbol),
        "as_of": last_date.strftime("%Y-%m-%d"),
        "last_close": last_close,
        "lookback": lookback,
        "horizon": horizon,
        "bias": bias,
        "regime": view["regime"],
        "stance": view["stance"],
        "blend_return_pct": round(blended_ret, 2),
        "analog_return_pct": analog["median_return_pct"],
        "analog_band": [analog["p25_return_pct"], analog["p75_return_pct"]],
        "n_analogs": analog["n_analogs"],
        "scanned": analog.get("scanned", 0),
        "analog_sources": analog.get("sources") or [],
        "trend_weight": round(w_trend, 2),
        "dates": future_dates,
        "path_blend": [round(v, 3) for v in blended],
        "path_analog": [round(v, 3) for v in analog_fwd],
        "path_low": [round(v, 3) for v in analog_low],
        "path_high": [round(v, 3) for v in analog_high],
        "path_trend": [round(v, 3) for v in trend],
        "history": history,
        "reasons": view["latest_reasons"],
        "disclaimer": (
            f"用本股近 {lookback} 日价+量+换手形态，在缓存池（扫描 {analog.get('scanned', 0)} 只）"
            f"中找相似窗口，取其后 {horizon} 日路径的中位与四分位；再与均线斜率外推按趋势强度拼合。"
            "预测区间越长，相似段后续分化越大，越不可靠，不能作为买卖依据。"
        ),
    }
