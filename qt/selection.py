"""底部反转与量价形态检测，供条件选股使用。

每个检测函数接收 ``qt.indicators.enrich`` 增强后的日线 DataFrame，
返回最近一根 K 线是否命中该形态。阈值统一收在模块顶部常量，便于调参。
所有规则都是经验启发式，不构成投资建议，也不能保证收益。
"""

from __future__ import annotations

import pandas as pd

# 涨幅与量能阈值（百分比 / 倍数）
BIG_PCT = 7.0        # 大涨（含涨停）的最小当日涨幅
BIG_CANDLE_PCT = 5.0  # 单根「大阳线」的最小涨幅
VOL_SURGE = 1.8       # 相对 20 日均量的放量倍数
NEAR_MA = 0.02        # 收盘相对均线的偏离阈值（2% 内视为「贴近均线」）
FIRST_LOOKBACK = 20   # 判定「首板」时回看多少根没有大涨
LOW_WINDOW = 60       # 判定「底部」时回看多少根找低位
LOW_RANGE = 0.10      # 距区间低点的允许幅度


def _pct(close: pd.Series) -> pd.Series:
    return close.pct_change() * 100


def _yn(flag: bool) -> str:
    return "yes" if flag else "no"


def _near_ma(x: pd.DataFrame, near_ma: float = NEAR_MA) -> bool:
    """收盘价是否贴近 MA10 或 MA20（2% 内）。"""
    close = float(x["close"].iloc[-1])
    for col in ("sma10", "sma20"):
        if col not in x.columns:
            continue
        ma = x[col].iloc[-1]
        if pd.isna(ma) or not ma:
            continue
        ma = float(ma)
        if ma and abs(close - ma) / ma <= near_ma:
            return True
    return False


def is_first_limit_up(
    x: pd.DataFrame,
    big_pct: float = BIG_PCT,
    first_lookback: int = FIRST_LOOKBACK,
    low_window: int = LOW_WINDOW,
    low_range: float = LOW_RANGE,
) -> bool:
    """底部首板涨停/大涨。

    最近一根为大涨（含涨停），且启动前价格处于近期低位、此前若干根内没有
    过同级别大涨（即「首板」而非连续拉升中）。
    """
    if len(x) < low_window + 1:
        return False
    close = x["close"]
    pct = _pct(close)
    cur = float(pct.iloc[-1])
    if pd.isna(cur) or cur < big_pct:
        return False

    pre_close = float(close.iloc[-2])
    recent_low = float(close.iloc[-low_window:-1].min())
    at_bottom = pre_close <= recent_low * (1 + low_range)
    if "sma60" in x.columns:
        sma60 = x["sma60"].iloc[-2]
        if not pd.isna(sma60):
            at_bottom = at_bottom or (pre_close < float(sma60))

    prior = pct.iloc[-first_lookback - 1 : -1].dropna()
    first = prior.empty or bool((prior < big_pct).all())
    return bool(at_bottom and first)


def is_bull_pullback(
    x: pd.DataFrame,
    big_pct: float = BIG_CANDLE_PCT,
    min_days: int = 2,
    max_days: int = 6,
) -> bool:
    """底部大阳线后连续缩量回调到均线附近。

    最近 max_days 根内出现一根放量大阳线，其后 min_days~max_days 根缩量回踩
    （量能递减、回踩不深），且当前收盘贴近 MA10/MA20。
    """
    if len(x) < 40:
        return False
    close = x["close"]
    open_ = x["open"]
    volume = x["volume"]
    pct = _pct(close)
    vol_ma5 = volume.rolling(5).mean()
    big = (pct >= big_pct) & (volume > vol_ma5)
    n = len(x)
    for k in range(n - 2, max(n - 13, -1), -1):
        if not bool(big.iloc[k]):
            continue
        span = n - 1 - k
        if span < min_days or span > max_days:
            continue
        seg_close = close.iloc[k + 1 : n]
        seg_vol = volume.iloc[k + 1 : n]
        if len(seg_close) < 2:
            continue
        # 确实回踩了：最新收盘低于大阳线收盘
        pulled_back = float(seg_close.iloc[-1]) < float(close.iloc[k])
        # 缩量：回调段量能逐日递减，且最新量小于大阳线当日
        shrinking = bool((seg_vol.diff().dropna() < 0).all()) and float(seg_vol.iloc[-1]) < float(volume.iloc[k])
        # 不破位：回调最低价不跌破大阳线开盘
        not_broken = float(seg_close.min()) >= float(open_.iloc[k])
        if pulled_back and shrinking and not_broken and _near_ma(x):
            return True
    return False


def is_volume_breakout(
    x: pd.DataFrame,
    low_window: int = 120,
    vol_surge: float = VOL_SURGE,
    recent_days: int = 3,
    base_days: int = 20,
) -> bool:
    """底部历史低量后突然放量。

    价格处于中长期低位（贴近 low_window 日低点或低于 MA60），放量前量能安静，
    最近 recent_days 根内出现相对 20 日均量 vol_surge 倍以上的放量。
    """
    if len(x) < low_window:
        return False
    close = x["close"]
    volume = x["volume"]

    low = float(close.iloc[-low_window:].min())
    close_at_low = float(close.iloc[-1]) <= low * 1.15
    below_ma60 = False
    if "sma60" in x.columns:
        sma60 = x["sma60"].iloc[-1]
        if not pd.isna(sma60):
            below_ma60 = float(close.iloc[-1]) < float(sma60)

    base = float(volume.iloc[-recent_days - base_days : -recent_days].mean())
    prior_base = float(volume.iloc[-low_window:-recent_days].mean())
    quiet_before = base <= prior_base  # 放量前量能未显著放大

    vol_ma20 = volume.rolling(20).mean()
    recent = volume.iloc[-recent_days:]
    ma20_recent = vol_ma20.iloc[-recent_days:]
    surge = bool((recent > ma20_recent * vol_surge).any())

    return bool((close_at_low or below_ma60) and quiet_before and surge)


def detect(x: pd.DataFrame) -> dict:
    """返回最近一根 K 线的形态标记字典（值统一为 yes/no）。"""
    return {
        "first_limit_up": _yn(is_first_limit_up(x)),
        "bull_pullback": _yn(is_bull_pullback(x)),
        "vol_breakout": _yn(is_volume_breakout(x)),
    }
