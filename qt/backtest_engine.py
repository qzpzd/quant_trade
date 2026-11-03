"""Backtest runner with A-share lot size, costs, and analyzers."""

from __future__ import annotations

import math

import backtrader as bt
import pandas as pd

from qt.config import (
    DEFAULT_CASH,
    DEFAULT_COMMISSION,
    DEFAULT_LOT,
    DEFAULT_MIN_COMM,
    DEFAULT_STAMP,
)
from qt.data import bars_to_records, load_bars, stock_name
from qt.strategies import STRATEGIES


class AShareCommission(bt.CommInfoBase):
    params = (
        ("commission", DEFAULT_COMMISSION),
        ("stamp", DEFAULT_STAMP),
        ("min_comm", DEFAULT_MIN_COMM),
        ("stocklike", True),
        ("commtype", bt.CommInfoBase.COMM_PERC),
        ("percabs", True),
    )

    def _getcommission(self, size, price, pseudoexec):
        turnover = abs(size) * price
        comm = max(turnover * self.p.commission, self.p.min_comm)
        if size < 0:
            comm += turnover * self.p.stamp
        return comm


class ASharePercentSizer(bt.Sizer):
    params = (("percents", 95), ("lot", DEFAULT_LOT))

    def _getsizing(self, comminfo, cash, data, isbuy):
        position = self.broker.getposition(data)
        if not isbuy:
            return position.size
        price = data.close[0]
        if price <= 0:
            return 0
        size = int((cash * self.p.percents / 100.0) / price)
        size = (size // self.p.lot) * self.p.lot
        return max(size, 0)


class EquityAnalyzer(bt.Analyzer):
    def start(self):
        self.rows = []

    def next(self):
        self.rows.append(
            {
                "date": self.datas[0].datetime.date(0).isoformat(),
                "value": float(self.strategy.broker.getvalue()),
                "cash": float(self.strategy.broker.getcash()),
            }
        )

    def get_analysis(self):
        return self.rows


def _sharpe(returns: pd.Series, rf_annual: float = 0.02) -> float | None:
    if returns is None or len(returns) < 30:
        return None
    rf_daily = rf_annual / 252
    excess = returns - rf_daily
    std = float(excess.std())
    if std < 1e-12:
        return None
    return float(excess.mean() / std * math.sqrt(252))


def _max_drawdown(equity: list[dict]) -> float | None:
    if not equity:
        return None
    values = [e["value"] for e in equity]
    peak = values[0]
    max_dd = 0.0
    for v in values:
        peak = max(peak, v)
        if peak > 0:
            max_dd = min(max_dd, v / peak - 1)
    return float(max_dd * 100)


def _win_rate(trades: list[dict]) -> tuple[float | None, int]:
    round_trips = []
    pending = None
    for t in trades:
        if t["side"] == "buy":
            pending = t
        elif t["side"] == "sell" and pending:
            pnl = (t["price"] - pending["price"]) * t["size"] - t["comm"] - pending["comm"]
            round_trips.append(pnl)
            pending = None
    if not round_trips:
        return None, 0
    wins = sum(1 for p in round_trips if p > 0)
    return wins / len(round_trips) * 100, len(round_trips)


def run_backtest(
    symbol: str,
    strategy_key: str,
    start_date: str,
    end_date: str,
    cash: float = DEFAULT_CASH,
    commission: float = DEFAULT_COMMISSION,
    stamp: float = DEFAULT_STAMP,
    plot_path: str | None = None,
    verbose: bool = False,
    stop_loss_pct: float = 0.0,
) -> dict:
    if strategy_key not in STRATEGIES:
        raise ValueError(f"未知策略: {strategy_key}")
    label, cls = STRATEGIES[strategy_key]
    df = load_bars(symbol, start_date, end_date)
    if df.empty or len(df) < 30:
        raise RuntimeError("行情不足，无法回测（至少需要约 30 根日线）")

    cerebro = bt.Cerebro()
    data = bt.feeds.PandasData(dataname=df[["open", "high", "low", "close", "volume"]])
    cerebro.adddata(data)
    cerebro.addstrategy(cls, verbose=verbose, stop_loss_pct=stop_loss_pct)
    cerebro.broker.setcash(cash)
    cerebro.broker.set_coc(False)
    cerebro.broker.set_coo(False)
    cerebro.broker.addcommissioninfo(
        AShareCommission(commission=commission, stamp=stamp)
    )
    cerebro.addsizer(ASharePercentSizer, percents=95, lot=DEFAULT_LOT)
    cerebro.addanalyzer(EquityAnalyzer, _name="equity")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="ta")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="dd")

    results = cerebro.run()
    strat = results[0]
    equity = strat.analyzers.equity.get_analysis()
    trades = list(getattr(strat, "trade_log", []))
    final_value = float(cerebro.broker.getvalue())
    ret_pct = (final_value - cash) / cash * 100

    eq = pd.Series({e["date"]: e["value"] for e in equity}, dtype=float)
    eq.index = pd.to_datetime(eq.index)
    daily = eq.pct_change().dropna()

    bh_ret = float(df["close"].iloc[-1] / df["close"].iloc[0] - 1) * 100
    win_rate, n_rounds = _win_rate(trades)
    warning = None
    lot_cost = float(df["close"].median()) * DEFAULT_LOT
    if not trades and lot_cost > cash:
        warning = f"默认资金不足以买入 1 手（约 {lot_cost:.0f} 元），请加大资金后再回测。"

    if plot_path:
        _save_plot(cerebro, plot_path)

    return {
        "symbol": symbol,
        "name": stock_name(symbol),
        "strategy": strategy_key,
        "strategy_name": label,
        "start": start_date,
        "end": end_date,
        "cash": cash,
        "final_value": round(final_value, 2),
        "return_pct": round(ret_pct, 2),
        "buy_hold_pct": round(bh_ret, 2),
        "max_drawdown_pct": round(_max_drawdown(equity) or 0, 2),
        "sharpe": None if _sharpe(daily) is None else round(_sharpe(daily), 2),
        "trades": trades,
        "round_trips": n_rounds,
        "win_rate_pct": None if win_rate is None else round(win_rate, 1),
        "equity": equity,
        "bars": bars_to_records(df),
        "warning": warning,
    }


def _save_plot(cerebro: bt.Cerebro, plot_path: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figs = cerebro.plot(style="candlestick", iplot=False)
    if not figs:
        return
    fig = figs[0][0]
    fig.set_size_inches(16, 9)
    fig.savefig(plot_path, dpi=100)
    plt.close(fig)


def list_strategies() -> list[dict]:
    return [{"id": k, "name": v[0]} for k, v in STRATEGIES.items()]
