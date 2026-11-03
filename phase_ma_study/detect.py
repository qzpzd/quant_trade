"""阶段检测：基于收盘价相对 MA20 + MA5/MA20 排列划分上升/下降/震荡。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

import numpy as np
import pandas as pd

from .config import MA_PERIODS, MERGE_GAP_DAYS, MIN_PHASE_DAYS

PhaseKind = Literal["rise", "fall", "side"]


@dataclass
class Phase:
    symbol: str
    kind: PhaseKind
    i0: int
    i1: int  # inclusive index into df
    start: str
    end: str
    days: int
    open_px: float
    close_px: float
    high_px: float
    low_px: float
    ret_pct: float
    max_dd_pct: float
    avg_vol: float
    # MA 斜率（日均变化率 %）
    ma5_slope: float
    ma10_slope: float
    ma20_slope: float
    ma30_slope: float
    # 线性拟合：log(close) = a + b * t
    lin_a: float
    lin_b: float
    lin_r2: float
    # 二次：log(close) = c0 + c1*t + c2*t^2
    quad_c0: float
    quad_c1: float
    quad_c2: float
    quad_r2: float

    def to_dict(self) -> dict:
        return asdict(self)


def add_mas(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    close = out["close"].astype(float)
    for p in MA_PERIODS:
        out[f"ma{p}"] = close.rolling(p, min_periods=p).mean()
    return out


def _daily_state(row) -> int:
    """1=升 -1=降 0=震荡。"""
    c = row["close"]
    ma5, ma20 = row.get("ma5"), row.get("ma20")
    if pd.isna(ma5) or pd.isna(ma20) or pd.isna(c):
        return 0
    if c > ma20 and ma5 >= ma20:
        return 1
    if c < ma20 and ma5 <= ma20:
        return -1
    return 0


def _merge_runs(states: np.ndarray, gap: int) -> list[tuple[int, int, int]]:
    """合并连续同向片段，允许中间短暂震荡/反向不超过 gap 日。"""
    n = len(states)
    if n == 0:
        return []
    runs: list[tuple[int, int, int]] = []
    i = 0
    while i < n:
        s = int(states[i])
        if s == 0:
            i += 1
            continue
        j = i
        last_good = i
        while j < n:
            sj = int(states[j])
            if sj == s:
                last_good = j
                j += 1
            elif sj == 0 or sj == -s:
                # 向后看是否还能回到同向
                k = j
                while k < n and k - j <= gap and int(states[k]) != s:
                    k += 1
                if k < n and int(states[k]) == s and k - j <= gap:
                    j = k
                else:
                    break
            else:
                break
        runs.append((i, last_good, s))
        i = last_good + 1
    return runs


def _fit_log_price(closes: np.ndarray) -> dict:
    y = np.log(np.clip(closes.astype(float), 1e-8, None))
    t = np.arange(len(y), dtype=float)
    if len(y) < 3 or not np.isfinite(y).all():
        return {
            "lin_a": float("nan"),
            "lin_b": float("nan"),
            "lin_r2": float("nan"),
            "quad_c0": float("nan"),
            "quad_c1": float("nan"),
            "quad_c2": float("nan"),
            "quad_r2": float("nan"),
        }
    # linear
    b1, a1 = np.polyfit(t, y, 1)
    yhat1 = a1 + b1 * t
    ss_res1 = float(np.sum((y - yhat1) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2)) or 1.0
    r2_1 = 1.0 - ss_res1 / ss_tot
    # quadratic
    if len(y) >= 5:
        c2, c1, c0 = np.polyfit(t, y, 2)
        yhat2 = c0 + c1 * t + c2 * (t**2)
        r2_2 = 1.0 - float(np.sum((y - yhat2) ** 2)) / ss_tot
    else:
        c0, c1, c2, r2_2 = a1, b1, 0.0, r2_1
    return {
        "lin_a": float(a1),
        "lin_b": float(b1),
        "lin_r2": float(r2_1),
        "quad_c0": float(c0),
        "quad_c1": float(c1),
        "quad_c2": float(c2),
        "quad_r2": float(r2_2),
    }


def _ma_slope_pct(series: pd.Series) -> float:
    s = series.dropna()
    if len(s) < 2:
        return float("nan")
    a, b = float(s.iloc[0]), float(s.iloc[-1])
    if a <= 0:
        return float("nan")
    return (b / a - 1.0) * 100.0 / max(len(s) - 1, 1)


def detect_phases(symbol: str, df: pd.DataFrame, min_days: int = MIN_PHASE_DAYS) -> list[Phase]:
    if df is None or df.empty or len(df) < max(MA_PERIODS) + min_days:
        return []
    work = add_mas(df)
    states = work.apply(_daily_state, axis=1).to_numpy()
    runs = _merge_runs(states, MERGE_GAP_DAYS)
    phases: list[Phase] = []
    for i0, i1, s in runs:
        days = i1 - i0 + 1
        if days < min_days:
            continue
        seg = work.iloc[i0 : i1 + 1]
        closes = seg["close"].to_numpy(dtype=float)
        highs = seg["high"].to_numpy(dtype=float)
        lows = seg["low"].to_numpy(dtype=float)
        open_px = float(closes[0])
        close_px = float(closes[-1])
        ret_pct = (close_px / open_px - 1.0) * 100.0 if open_px else 0.0
        # 阶段内最大回撤（从峰值）
        peak = np.maximum.accumulate(closes)
        dd = (closes / peak - 1.0) * 100.0
        max_dd = float(dd.min()) if len(dd) else 0.0
        kind: PhaseKind = "rise" if s > 0 else "fall"
        # 若方向与收益矛盾，以收益修正（噪声）
        if kind == "rise" and ret_pct < -1:
            kind = "fall"
        elif kind == "fall" and ret_pct > 1:
            kind = "rise"
        fit = _fit_log_price(closes)
        start = seg.index[0]
        end = seg.index[-1]
        phases.append(
            Phase(
                symbol=symbol,
                kind=kind,
                i0=int(i0),
                i1=int(i1),
                start=str(pd.Timestamp(start).date()),
                end=str(pd.Timestamp(end).date()),
                days=int(days),
                open_px=open_px,
                close_px=close_px,
                high_px=float(np.nanmax(highs)),
                low_px=float(np.nanmin(lows)),
                ret_pct=float(ret_pct),
                max_dd_pct=max_dd,
                avg_vol=float(seg["volume"].astype(float).mean()) if "volume" in seg else float("nan"),
                ma5_slope=_ma_slope_pct(seg["ma5"]),
                ma10_slope=_ma_slope_pct(seg["ma10"]),
                ma20_slope=_ma_slope_pct(seg["ma20"]),
                ma30_slope=_ma_slope_pct(seg["ma30"]),
                **fit,
            )
        )
    return phases
