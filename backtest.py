"""CLI-compatible wrapper around the A-share backtest engine."""

from qt.backtest_engine import run_backtest as _run
from qt.strategies import STRATEGIES


def _key_for(strategy_class):
    for key, (_name, cls) in STRATEGIES.items():
        if cls is strategy_class:
            return key
    raise ValueError(f"未知策略类: {strategy_class}")


def run_backtest(
    strategy_class,
    symbol,
    start_date,
    end_date,
    cash=100000.0,
    commission=0.00025,
    plot=False,
    plot_path=None,
):
    """Keep the original positional signature used by main.py."""
    result = _run(
        symbol,
        _key_for(strategy_class),
        start_date,
        end_date,
        cash=cash,
        commission=commission,
        plot_path=plot_path if plot else None,
        verbose=True,
    )
    return result


if __name__ == "__main__":
    from qt.strategies import TrendFollowingStrategy

    run_backtest(TrendFollowingStrategy, "000001", "20200101", "20231231")
