"""Backtrader strategies with optional trade recording and quiet logs."""

from __future__ import annotations

import backtrader as bt
import numpy as np


class BaseStrategy(bt.Strategy):
    params = (("verbose", False), ("stop_loss_pct", 0.0))

    def __init__(self):
        self.order = None
        self.trade_log = []
        self._entry_price = None

    def log(self, txt, dt=None):
        if not self.p.verbose:
            return
        dt = dt or self.datas[0].datetime.date(0)
        print(f"{dt.isoformat()}, {txt}")

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status == order.Completed:
            side = "buy" if order.isbuy() else "sell"
            rec = {
                "date": self.datas[0].datetime.date(0).isoformat(),
                "side": side,
                "price": float(order.executed.price),
                "size": float(abs(order.executed.size)),
                "value": float(abs(order.executed.value)),
                "comm": float(order.executed.comm),
            }
            self.trade_log.append(rec)
            self.log(f"{side} {rec['price']:.2f} x {rec['size']:.0f}")
            if order.isbuy():
                self._entry_price = rec["price"]
            else:
                self._entry_price = None
        self.order = None

    def _blocked(self) -> bool:
        return bool(self.order)

    def _stop_hit(self) -> bool:
        pct = float(self.p.stop_loss_pct or 0)
        if pct <= 0 or not self.position or not self._entry_price:
            return False
        return float(self.data.close[0]) <= self._entry_price * (1 - pct / 100.0)

    def _should_exit(self, signal: bool) -> bool:
        if self._blocked() or not self.position:
            return False
        return bool(signal) or self._stop_hit()


class TrendFollowingStrategy(BaseStrategy):
    params = (
        ("ema_short", 20),
        ("ema_long", 60),
        ("rsi_period", 14),
        ("rsi_buy_level", 70),
        ("rsi_sell_level", 80),
        ("verbose", False),
        ("stop_loss_pct", 0.0),
    )

    def __init__(self):
        super().__init__()
        self.ema_short = bt.indicators.EMA(self.data.close, period=self.p.ema_short)
        self.ema_long = bt.indicators.EMA(self.data.close, period=self.p.ema_long)
        self.rsi = bt.indicators.RSI(self.data.close, period=self.p.rsi_period)
        self.crossover = bt.indicators.CrossOver(self.ema_short, self.ema_long)

    def next(self):
        if self._blocked():
            return
        if not self.position:
            if self.crossover > 0 and self.rsi < self.p.rsi_buy_level:
                self.order = self.buy()
        elif self._should_exit(self.crossover < 0 or self.rsi > self.p.rsi_sell_level):
            self.order = self.sell()


class RSIStrategy(BaseStrategy):
    params = (
        ("rsi_period", 14),
        ("rsi_overbought", 70),
        ("rsi_oversold", 30),
        ("verbose", False),
        ("stop_loss_pct", 0.0),
    )

    def __init__(self):
        super().__init__()
        self.rsi = bt.indicators.RSI(self.data.close, period=self.p.rsi_period)

    def next(self):
        if self._blocked():
            return
        if not self.position:
            if self.rsi < self.p.rsi_oversold:
                self.order = self.buy()
        elif self._should_exit(self.rsi > self.p.rsi_overbought):
            self.order = self.sell()


class BollingerBandsStrategy(BaseStrategy):
    params = (
        ("period", 20),
        ("devfactor", 2.0),
        ("verbose", False),
        ("stop_loss_pct", 0.0),
    )

    def __init__(self):
        super().__init__()
        self.bband = bt.indicators.BollingerBands(
            self.data.close, period=self.p.period, devfactor=self.p.devfactor
        )

    def next(self):
        if self._blocked():
            return
        if not self.position:
            if self.data.close < self.bband.lines.bot:
                self.order = self.buy()
        elif self._should_exit(self.data.close > self.bband.lines.top):
            self.order = self.sell()


class MACDStrategy(BaseStrategy):
    params = (
        ("fast_period", 12),
        ("slow_period", 26),
        ("signal_period", 9),
        ("verbose", False),
        ("stop_loss_pct", 0.0),
    )

    def __init__(self):
        super().__init__()
        self.macd = bt.indicators.MACD(
            self.data.close,
            period_me1=self.p.fast_period,
            period_me2=self.p.slow_period,
            period_signal=self.p.signal_period,
        )
        self.crossover = bt.indicators.CrossOver(self.macd.macd, self.macd.signal)

    def next(self):
        if self._blocked():
            return
        if not self.position:
            if self.crossover > 0:
                self.order = self.buy()
        elif self._should_exit(self.crossover < 0):
            self.order = self.sell()


class SuperTrendIndicator(bt.Indicator):
    lines = ("st", "dir")
    params = (("period", 10), ("multiplier", 3.0))

    def __init__(self):
        self.atr = bt.indicators.ATR(period=self.p.period)
        self.addminperiod(self.p.period)
        self.fu = None
        self.fl = None
        self.trend = 1

    def next(self):
        hl2 = (self.data.high[0] + self.data.low[0]) / 2.0
        upper = hl2 + self.p.multiplier * self.atr[0]
        lower = hl2 - self.p.multiplier * self.atr[0]
        if self.fu is None or not np.isfinite(self.fu):
            self.fu = upper
            self.fl = lower
            self.trend = 1
            self.l.st[0] = lower
            self.l.dir[0] = 1
            return
        self.fu = upper if (upper < self.fu or self.data.close[-1] > self.fu) else self.fu
        self.fl = lower if (lower > self.fl or self.data.close[-1] < self.fl) else self.fl
        if self.trend == 1:
            if self.data.close[0] < self.fl:
                self.trend = -1
                self.l.st[0] = self.fu
            else:
                self.l.st[0] = self.fl
        else:
            if self.data.close[0] > self.fu:
                self.trend = 1
                self.l.st[0] = self.fl
            else:
                self.l.st[0] = self.fu
        self.l.dir[0] = self.trend


class SuperTrendStrategy(BaseStrategy):
    params = (
        ("period", 10),
        ("multiplier", 3.0),
        ("verbose", False),
        ("stop_loss_pct", 0.0),
    )

    def __init__(self):
        super().__init__()
        self.st = SuperTrendIndicator(
            self.data, period=self.p.period, multiplier=self.p.multiplier
        )

    def next(self):
        if self._blocked():
            return
        if not self.position:
            if self.st.dir[0] > 0 and self.st.dir[-1] <= 0:
                self.order = self.buy()
        elif self._should_exit(self.st.dir[0] < 0):
            self.order = self.sell()


class TurtleStrategy(BaseStrategy):
    params = (
        ("entry_period", 20),
        ("exit_period", 10),
        ("verbose", False),
        ("stop_loss_pct", 0.0),
    )

    def __init__(self):
        super().__init__()
        self.entry_ch = bt.indicators.Highest(self.data.high, period=self.p.entry_period)
        self.exit_ch = bt.indicators.Lowest(self.data.low, period=self.p.exit_period)

    def next(self):
        if self._blocked():
            return
        if not self.position:
            if self.data.close[0] > self.entry_ch[-1]:
                self.order = self.buy()
        elif self._should_exit(self.data.close[0] < self.exit_ch[-1]):
            self.order = self.sell()


class DualThrustStrategy(BaseStrategy):
    params = (
        ("n", 4),
        ("k1", 0.5),
        ("k2", 0.5),
        ("verbose", False),
        ("stop_loss_pct", 0.0),
    )

    def __init__(self):
        super().__init__()
        self.hh = bt.indicators.Highest(self.data.high, period=self.p.n)
        self.hc = bt.indicators.Highest(self.data.close, period=self.p.n)
        self.lc = bt.indicators.Lowest(self.data.close, period=self.p.n)
        self.ll = bt.indicators.Lowest(self.data.low, period=self.p.n)

    def next(self):
        if self._blocked():
            return
        rng = max(self.hh[-1] - self.lc[-1], self.hc[-1] - self.ll[-1])
        buy_line = self.data.open[0] + self.p.k1 * rng
        sell_line = self.data.open[0] - self.p.k2 * rng
        if not self.position:
            if self.data.close[0] > buy_line:
                self.order = self.buy()
        elif self._should_exit(self.data.close[0] < sell_line):
            self.order = self.sell()


class RSI2Strategy(BaseStrategy):
    """Connors RSI(2) mean-reversion, SMA20 as trend filter (A-share friendly)."""

    params = (
        ("rsi_period", 2),
        ("rsi_buy", 10),
        ("sma_trend", 20),
        ("sma_exit", 5),
        ("verbose", False),
        ("stop_loss_pct", 0.0),
    )

    def __init__(self):
        super().__init__()
        self.rsi2 = bt.indicators.RSI(
            self.data.close, period=self.p.rsi_period, safediv=True
        )
        self.sma_trend = bt.indicators.SMA(self.data.close, period=self.p.sma_trend)
        self.sma_exit = bt.indicators.SMA(self.data.close, period=self.p.sma_exit)

    def next(self):
        if self._blocked():
            return
        if not self.position:
            if self.data.close[0] > self.sma_trend[0] and self.rsi2[0] < self.p.rsi_buy:
                self.order = self.buy()
        elif self._should_exit(self.data.close[0] > self.sma_exit[0]):
            self.order = self.sell()


STRATEGIES = {
    "trend": ("趋势追踪", TrendFollowingStrategy),
    "rsi": ("RSI 反转", RSIStrategy),
    "bollinger": ("布林带", BollingerBandsStrategy),
    "macd": ("MACD", MACDStrategy),
    "supertrend": ("SuperTrend", SuperTrendStrategy),
    "turtle": ("海龟突破", TurtleStrategy),
    "dual_thrust": ("Dual Thrust", DualThrustStrategy),
    "rsi2": ("RSI2 回归", RSI2Strategy),
}
