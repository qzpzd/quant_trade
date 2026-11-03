"""Buy / sell point detection with human-readable reasons."""

from __future__ import annotations

import pandas as pd

from qt.indicators import enrich, last_snapshot


def _cross_up(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a > b) & (a.shift(1) <= b.shift(1))


def _cross_down(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a < b) & (a.shift(1) >= b.shift(1))


def detect_signals(df: pd.DataFrame) -> list[dict]:
    if df is None or len(df) < 60:
        return []
    x = enrich(df)
    events: list[dict] = []

    def add(mask: pd.Series, action: str, source: str, reason_fn, strength: float):
        hits = x.index[mask.fillna(False)]
        for ts in hits:
            row = x.loc[ts]
            events.append(
                {
                    "date": pd.Timestamp(ts).strftime("%Y-%m-%d"),
                    "action": action,
                    "source": source,
                    "price": float(row["close"]),
                    "strength": strength,
                    "reason": reason_fn(row),
                }
            )

    add(
        _cross_up(x["ema20"], x["ema60"]) & (x["rsi14"] < 70),
        "buy",
        "趋势追踪",
        lambda r: f"EMA20 上穿 EMA60（金叉），RSI={r['rsi14']:.1f} 未超买",
        0.72,
    )
    add(
        _cross_down(x["ema20"], x["ema60"]) | (x["rsi14"] > 80),
        "sell",
        "趋势追踪",
        lambda r: f"EMA 死叉或 RSI 过热（RSI={r['rsi14']:.1f}）",
        0.7,
    )
    add(
        (x["rsi14"] < 30) & (x["rsi14"].shift(1) >= 30),
        "buy",
        "RSI 反转",
        lambda r: f"RSI 跌破 30 进入超卖（{r['rsi14']:.1f}）",
        0.68,
    )
    add(
        (x["rsi14"] > 70) & (x["rsi14"].shift(1) <= 70),
        "sell",
        "RSI 反转",
        lambda r: f"RSI 升破 70 进入超买（{r['rsi14']:.1f}）",
        0.68,
    )
    add(
        (x["close"] < x["bb_lower"]) & (x["close"].shift(1) >= x["bb_lower"].shift(1)),
        "buy",
        "布林带",
        lambda r: f"收盘跌破布林下轨（{r['bb_lower']:.2f}）",
        0.64,
    )
    add(
        (x["close"] > x["bb_upper"]) & (x["close"].shift(1) <= x["bb_upper"].shift(1)),
        "sell",
        "布林带",
        lambda r: f"收盘升破布林上轨（{r['bb_upper']:.2f}）",
        0.64,
    )
    add(
        _cross_up(x["macd_dif"], x["macd_dea"]),
        "buy",
        "MACD",
        lambda r: f"DIF 上穿 DEA 金叉，柱={r['macd_hist']:.3f}",
        0.7,
    )
    add(
        _cross_down(x["macd_dif"], x["macd_dea"]),
        "sell",
        "MACD",
        lambda r: f"DIF 下穿 DEA 死叉，柱={r['macd_hist']:.3f}",
        0.7,
    )
    add(
        _cross_up(x["sma5"], x["sma20"]) & (x["vol_ratio"] > 1.3),
        "buy",
        "均量突破",
        lambda r: f"MA5 上穿 MA20 且量比 {r['vol_ratio']:.2f}",
        0.6,
    )
    add(
        _cross_up(x["kdj_k"], x["kdj_d"]) & (x["kdj_j"] < 30),
        "buy",
        "KDJ",
        lambda r: f"KDJ 低位金叉（J={r['kdj_j']:.1f}）",
        0.58,
    )
    add(
        _cross_down(x["kdj_k"], x["kdj_d"]) & (x["kdj_j"] > 70),
        "sell",
        "KDJ",
        lambda r: f"KDJ 高位死叉（J={r['kdj_j']:.1f}）",
        0.58,
    )
    add(
        (x["st_dir"] > 0) & (x["st_dir"].shift(1) <= 0),
        "buy",
        "SuperTrend",
        lambda r: f"SuperTrend 翻多，轨={r['st_line']:.2f}",
        0.74,
    )
    add(
        (x["st_dir"] < 0) & (x["st_dir"].shift(1) >= 0),
        "sell",
        "SuperTrend",
        lambda r: f"SuperTrend 翻空，轨={r['st_line']:.2f}",
        0.74,
    )
    add(
        (x["close"] > x["dc_high"]) & (x["close"].shift(1) <= x["dc_high"].shift(1)),
        "buy",
        "海龟突破",
        lambda r: f"收盘突破 20 日通道上沿（{r['dc_high']:.2f}）",
        0.73,
    )
    add(
        (x["close"] < x["dc_low"]) & (x["close"].shift(1) >= x["dc_low"].shift(1)),
        "sell",
        "海龟突破",
        lambda r: f"收盘跌破 10 日通道下沿（{r['dc_low']:.2f}）",
        0.72,
    )
    add(
        (x["close"] > x["dt_buy"]) & (x["close"].shift(1) <= x["dt_buy"].shift(1)),
        "buy",
        "Dual Thrust",
        lambda r: f"收盘升破开盘上轨（{r['dt_buy']:.2f}）",
        0.7,
    )
    add(
        (x["close"] < x["dt_sell"]) & (x["close"].shift(1) >= x["dt_sell"].shift(1)),
        "sell",
        "Dual Thrust",
        lambda r: f"收盘跌破开盘下轨（{r['dt_sell']:.2f}）",
        0.7,
    )
    add(
        (x["rsi2"] < 10) & (x["rsi2"].shift(1) >= 10) & (x["close"] > x["sma20"]),
        "buy",
        "RSI2 回归",
        lambda r: f"RSI(2)={r['rsi2']:.1f} 超卖且价格在 MA20 上方",
        0.71,
    )
    add(
        (x["close"] > x["sma5"]) & (x["close"].shift(1) <= x["sma5"].shift(1)) & (x["rsi2"] > 50),
        "sell",
        "RSI2 回归",
        lambda r: f"收盘站上 MA5（{r['sma5']:.2f}），RSI(2)={r['rsi2']:.1f}",
        0.66,
    )

    events.sort(key=lambda e: e["date"])
    return events


def _regime(snap: dict) -> tuple[str, str]:
    adx_v = snap.get("adx14") or 0
    ema20 = snap.get("ema20") or 0
    ema60 = snap.get("ema60") or 0
    close = snap.get("close") or 0
    if adx_v >= 25 and close >= ema20 >= ema60:
        return "上升趋势", "ADX 偏强且均线多头排列，价格在短期均线上方。"
    if adx_v >= 25 and close <= ema20 <= ema60:
        return "下降趋势", "ADX 偏强且均线空头排列，价格在短期均线下方。"
    return "震荡整理", "ADX 不高或均线纠缠，更接近区间波动而非单边趋势。"


def current_view(df: pd.DataFrame, lookback_signals: int = 60) -> dict:
    x = enrich(df)
    snap = last_snapshot(x)
    signals = detect_signals(df)
    if signals:
        cutoff = x.index[-1] - pd.Timedelta(days=lookback_signals)
        recent = [s for s in signals if pd.Timestamp(s["date"]) >= cutoff]
    else:
        recent = []

    last_n = recent[-8:]
    score = 0.0
    reasons = []
    for s in last_n:
        delta = s["strength"] if s["action"] == "buy" else -s["strength"]
        # Recency: last 10 trading days weigh more
        age = (x.index[-1] - pd.Timestamp(s["date"])).days
        w = 1.0 if age <= 10 else 0.45
        score += delta * w
        if age <= 15:
            reasons.append(s)

    if score > 0.45:
        stance = "偏多"
        stance_id = "buy"
    elif score < -0.45:
        stance = "偏空"
        stance_id = "sell"
    else:
        stance = "观望"
        stance_id = "hold"

    # Last-bar overlays that have not yet "crossed" but are extreme.
    extras = []
    rsi_v = snap.get("rsi14")
    if rsi_v is not None and rsi_v < 30:
        extras.append({"action": "buy", "source": "RSI", "reason": f"当前 RSI={rsi_v:.1f} 仍在超卖区", "strength": 0.5})
    if rsi_v is not None and rsi_v > 70:
        extras.append({"action": "sell", "source": "RSI", "reason": f"当前 RSI={rsi_v:.1f} 仍在超买区", "strength": 0.5})
    rsi2_v = snap.get("rsi2")
    if rsi2_v is not None and rsi2_v < 10 and (snap.get("close") or 0) > (snap.get("sma20") or 0):
        extras.append({"action": "buy", "source": "RSI2", "reason": f"当前 RSI(2)={rsi2_v:.1f} 且位于均线上方", "strength": 0.52})
    close = snap.get("close")
    lower = snap.get("bb_lower")
    upper = snap.get("bb_upper")
    if close and lower and close < lower:
        extras.append({"action": "buy", "source": "布林带", "reason": "现价仍在布林下轨下方", "strength": 0.45})
    if close and upper and close > upper:
        extras.append({"action": "sell", "source": "布林带", "reason": "现价仍在布林上轨上方", "strength": 0.45})

    regime, regime_reason = _regime(snap)
    return {
        "snapshot": snap,
        "regime": regime,
        "regime_reason": regime_reason,
        "stance": stance,
        "stance_id": stance_id,
        "score": round(score, 3),
        "signals": recent,
        "latest_reasons": reasons[-6:] + extras,
        "disclaimer": "信号来自公开行情与技术规则，不是投资建议，也不能预测确定收益。",
    }
