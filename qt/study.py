"""Compare similar-pattern hits: stance, forecast, and a simple buy shortlist."""

from __future__ import annotations

from qt.data import load_bars, load_cached_bars, stock_name
from qt.predict import forecast
from qt.signals import current_view


def _bars(symbol: str):
    df = load_cached_bars(symbol)
    if df is not None and not df.empty:
        return df
    return load_bars(symbol, "20180101", None)


def _score(
    view: dict,
    pred: dict | None,
    corr: float,
    n_patterns: int,
    corr_volume: float | None = None,
    corr_turnover: float | None = None,
) -> tuple[int, bool, str]:
    stance = view.get("stance_id") or "hold"
    pts = 0
    bits = []
    if stance == "buy":
        pts += 3
        bits.append("买卖点偏多")
    elif stance == "sell":
        pts -= 2
        bits.append("买卖点偏空")
    else:
        bits.append("买卖点观望")
    if pred:
        bias = pred.get("bias")
        ret = pred.get("blend_return_pct") or 0
        if bias == "偏上涨":
            pts += 2
            bits.append(f"预测偏上涨 {ret:+.1f}%")
        elif bias == "偏下跌":
            pts -= 2
            bits.append(f"预测偏下跌 {ret:+.1f}%")
        elif ret > 0:
            pts += 1
            bits.append(f"合成路径 {ret:+.1f}%")
    if corr >= 0.8:
        pts += 2
        bits.append(f"形态相关 {corr:.2f}")
    elif corr >= 0.65:
        pts += 1
        bits.append(f"形态相关 {corr:.2f}")
    if corr_volume is not None and corr_volume >= 0.6:
        pts += 1
        bits.append(f"量能相关 {corr_volume:.2f}")
    if corr_turnover is not None and corr_turnover >= 0.55:
        pts += 1
        bits.append(f"换手相关 {corr_turnover:.2f}")
    snap = view.get("snapshot") or {}
    vol_ratio = snap.get("vol_ratio")
    if vol_ratio is not None and vol_ratio >= 1.3 and stance != "sell":
        pts += 1
        bits.append(f"量比 {float(vol_ratio):.2f}")
    if n_patterns >= 2:
        pts += 1
        bits.append(f"命中 {n_patterns} 个形态")
    bias = (pred or {}).get("bias")
    suitable = pts >= 3 and stance != "sell" and bias != "偏下跌"
    return pts, suitable, "；".join(bits)


def study_hits(hits: list[dict], limit: int = 12) -> dict:
    rows = []
    for h in hits[:limit]:
        code = h.get("symbol")
        if not code:
            continue
        try:
            df = _bars(code)
        except Exception:
            continue
        if df is None or df.empty or len(df) < 60:
            continue
        view = current_view(df.iloc[-160:] if len(df) > 160 else df)
        pred = None
        try:
            pred = forecast(code, lookback=20, horizon=8)
        except Exception:
            pred = None
        n_pat = int(h.get("n_patterns") or (1 if h.get("corr") is not None else 0))
        corr = float(h.get("corr") or 0)
        corr_volume = h.get("corr_volume")
        corr_turnover = h.get("corr_turnover")
        if corr_volume is not None:
            corr_volume = float(corr_volume)
        if corr_turnover is not None:
            corr_turnover = float(corr_turnover)
        score, suitable, why = _score(view, pred, corr, n_pat, corr_volume, corr_turnover)
        snap = view.get("snapshot") or {}
        rows.append(
            {
                "symbol": code,
                "name": h.get("name") or stock_name(code),
                "corr": corr,
                "corr_price": h.get("corr_price"),
                "corr_volume": corr_volume,
                "corr_turnover": corr_turnover,
                "avg_corr": h.get("avg_corr"),
                "n_patterns": n_pat,
                "match_start": h.get("start"),
                "match_end": h.get("end"),
                "forward_5": h.get("forward_5"),
                "forward_10": h.get("forward_10"),
                "patterns": h.get("patterns") or [],
                "stance": view.get("stance"),
                "stance_id": view.get("stance_id"),
                "regime": view.get("regime"),
                "rsi14": None if snap.get("rsi14") is None else round(float(snap["rsi14"]), 1),
                "vol_ratio": None if snap.get("vol_ratio") is None else round(float(snap["vol_ratio"]), 2),
                "close": None if snap.get("close") is None else round(float(snap["close"]), 3),
                "reasons": (view.get("latest_reasons") or [])[:4],
                "bias": None if pred is None else pred.get("bias"),
                "blend_return_pct": None if pred is None else pred.get("blend_return_pct"),
                "analog_return_pct": None if pred is None else pred.get("analog_return_pct"),
                "analog_band": None if pred is None else pred.get("analog_band"),
                "score": score,
                "suitable": suitable,
                "why": why,
            }
        )

    picks = sorted([r for r in rows if r["suitable"]], key=lambda x: (x["score"], x["corr"]), reverse=True)
    rows.sort(key=lambda x: (x["suitable"], x["score"], x["corr"]), reverse=True)
    return {
        "rows": rows,
        "picks": picks[:8],
        "disclaimer": "对比、买卖与预测都基于缓存日线和技术规则（含成交量/换手），不是投资建议，也不能保证收益。",
    }
