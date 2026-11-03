"""Technical indicators on OHLCV frames (datetime index)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _rma(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(alpha=1 / period, adjust=False).mean()


def sma(close: pd.Series, period: int) -> pd.Series:
    return close.rolling(period, min_periods=period).mean()


def ema(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = _rma(gain, period)
    avg_loss = _rma(loss, period)
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    out = out.mask(avg_loss.eq(0) & avg_gain.gt(0), 100.0)
    out = out.mask(avg_loss.eq(0) & avg_gain.eq(0), 50.0)
    return out


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    dif = ema(close, fast) - ema(close, slow)
    dea = ema(dif, signal)
    hist = (dif - dea) * 2
    return pd.DataFrame({"dif": dif, "dea": dea, "hist": hist})


def bollinger(close: pd.Series, period: int = 20, n_std: float = 2.0) -> pd.DataFrame:
    mid = sma(close, period)
    std = close.rolling(period, min_periods=period).std()
    upper = mid + n_std * std
    lower = mid - n_std * std
    width = (upper - lower) / mid.replace(0, np.nan)
    pct_b = (close - lower) / (upper - lower).replace(0, np.nan)
    return pd.DataFrame({"mid": mid, "upper": upper, "lower": lower, "width": width, "pct_b": pct_b})


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return _rma(tr, period)


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low = df["high"], df["low"]
    up = high.diff()
    down = -low.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr_atr = atr(df, period)
    plus_di = 100 * _rma(pd.Series(plus_dm, index=df.index), period) / tr_atr.replace(0, np.nan)
    minus_di = 100 * _rma(pd.Series(minus_dm, index=df.index), period) / tr_atr.replace(0, np.nan)
    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
    return _rma(dx, period)


def kdj(df: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3) -> pd.DataFrame:
    low_n = df["low"].rolling(n, min_periods=n).min()
    high_n = df["high"].rolling(n, min_periods=n).max()
    rsv = (df["close"] - low_n) / (high_n - low_n).replace(0, np.nan) * 100
    k = rsv.ewm(alpha=1 / m1, adjust=False).mean()
    d = k.ewm(alpha=1 / m2, adjust=False).mean()
    j = 3 * k - 2 * d
    return pd.DataFrame({"k": k, "d": d, "j": j})


def volume_ratio(volume: pd.Series, period: int = 5) -> pd.Series:
    """日线量比：当日成交量 / 过去 period 日均量（不含当日），对齐同花顺等常见日线口径。"""
    past_avg = volume.shift(1).rolling(period, min_periods=period).mean()
    return volume / past_avg


def supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    """ATR trailing stop; dir=1 多头, dir=-1 空头."""
    atr_s = atr(df, period).to_numpy()
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    hl2 = (high + low) / 2.0
    upper = hl2 + multiplier * atr_s
    lower = hl2 - multiplier * atr_s
    n = len(df)
    fu = np.copy(upper)
    fl = np.copy(lower)
    line = np.full(n, np.nan)
    direction = np.full(n, np.nan)
    trend = 1
    for i in range(n):
        if not np.isfinite(atr_s[i]):
            continue
        if i == 0 or not np.isfinite(fu[i - 1]):
            fu[i] = upper[i]
            fl[i] = lower[i]
            line[i] = lower[i]
            direction[i] = 1
            trend = 1
            continue
        fu[i] = upper[i] if (upper[i] < fu[i - 1] or close[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lower[i] if (lower[i] > fl[i - 1] or close[i - 1] < fl[i - 1]) else fl[i - 1]
        if trend == 1:
            if close[i] < fl[i]:
                trend = -1
                line[i] = fu[i]
            else:
                line[i] = fl[i]
        else:
            if close[i] > fu[i]:
                trend = 1
                line[i] = fl[i]
            else:
                line[i] = fu[i]
        direction[i] = trend
    return pd.DataFrame({"line": line, "dir": direction}, index=df.index)


def dual_thrust_range(df: pd.DataFrame, n: int = 4) -> pd.Series:
    hh = df["high"].rolling(n, min_periods=n).max().shift(1)
    hc = df["close"].rolling(n, min_periods=n).max().shift(1)
    lc = df["close"].rolling(n, min_periods=n).min().shift(1)
    ll = df["low"].rolling(n, min_periods=n).min().shift(1)
    return pd.concat([hh - lc, hc - ll], axis=1).max(axis=1)


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Attach common indicators used across analysis, screen, and charts."""
    out = df.copy()
    close = out["close"]
    out["sma5"] = sma(close, 5)
    out["sma10"] = sma(close, 10)
    out["sma20"] = sma(close, 20)
    out["sma60"] = sma(close, 60)
    out["ema20"] = ema(close, 20)
    out["ema60"] = ema(close, 60)
    out["rsi14"] = rsi(close, 14)
    out["rsi2"] = rsi(close, 2)
    mac = macd(close)
    out["macd_dif"] = mac["dif"]
    out["macd_dea"] = mac["dea"]
    out["macd_hist"] = mac["hist"]
    bb = bollinger(close)
    out["bb_mid"] = bb["mid"]
    out["bb_upper"] = bb["upper"]
    out["bb_lower"] = bb["lower"]
    out["bb_pct_b"] = bb["pct_b"]
    out["bb_width"] = bb["width"]
    out["atr14"] = atr(out, 14)
    out["adx14"] = adx(out, 14)
    kdj_df = kdj(out)
    out["kdj_k"] = kdj_df["k"]
    out["kdj_d"] = kdj_df["d"]
    out["kdj_j"] = kdj_df["j"]
    out["vol_ratio"] = volume_ratio(out["volume"], 5)
    out["pct_5"] = close.pct_change(5) * 100
    out["pct_10"] = close.pct_change(10) * 100
    out["pct_20"] = close.pct_change(20) * 100
    st = supertrend(out)
    out["st_line"] = st["line"]
    out["st_dir"] = st["dir"]
    out["dc_high"] = out["high"].rolling(20, min_periods=20).max().shift(1)
    out["dc_low"] = out["low"].rolling(10, min_periods=10).min().shift(1)
    dt_rng = dual_thrust_range(out, 4)
    out["dt_buy"] = out["open"] + 0.5 * dt_rng
    out["dt_sell"] = out["open"] - 0.5 * dt_rng
    return out


def last_snapshot(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    row = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else row
    snap = {}
    for col in df.columns:
        val = row[col]
        snap[col] = None if pd.isna(val) else float(val)
    snap["date"] = pd.Timestamp(df.index[-1]).strftime("%Y-%m-%d")
    snap["prev_close"] = float(prev["close"])
    return snap
