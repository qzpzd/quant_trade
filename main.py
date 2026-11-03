import argparse
import os

from qt.backtest_engine import run_backtest
from qt.config import DEFAULT_CASH, DEFAULT_COMMISSION
from qt.strategies import STRATEGIES


STRATEGY_LABELS = {
    key: name if name.endswith("策略") else f"{name}策略" for key, (name, _) in STRATEGIES.items()
}


def parse_args():
    parser = argparse.ArgumentParser(description="形迹 CLI 回测（缓存行情 + A 股成本）")
    parser.add_argument("--symbol", default="002195", help="股票代码")
    parser.add_argument("--start", default="20200101", help="起始日期 YYYYMMDD 或 YYYY-MM-DD")
    parser.add_argument("--end", default="20231231", help="结束日期")
    parser.add_argument("--cash", type=float, default=DEFAULT_CASH, help="初始资金")
    parser.add_argument(
        "--strategy",
        default="all",
        choices=["all", *STRATEGY_LABELS],
        help="策略，默认全部",
    )
    parser.add_argument("--no-plot", action="store_true", help="只打印指标，不生成 PNG")
    parser.add_argument(
        "--stop-loss",
        type=float,
        default=0.0,
        help="可选止损百分比，0 表示关闭（默认关闭，不影响现有结果）",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    stock_symbol = args.symbol
    start_date = args.start
    end_date = args.end
    initial_cash = args.cash
    keys = list(STRATEGY_LABELS) if args.strategy == "all" else [args.strategy]

    plots_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plots")
    os.makedirs(plots_dir, exist_ok=True)

    print("-" * 50)
    print("量化策略回测启动...")
    print(f"目标股票: {stock_symbol}")
    print(f"回测区间: {start_date} 至 {end_date}")
    print(f"初始资金: {initial_cash:.2f}")
    print(f"成本: 佣金 {DEFAULT_COMMISSION:.4%} + 卖出印花税，手数 100")
    print("-" * 50)

    for key in keys:
        name = STRATEGY_LABELS[key]
        print(f"\n========== 正在回测: {name} ==========")
        plot_path = None
        if not args.no_plot:
            plot_path = os.path.join(plots_dir, f"{name}_{stock_symbol}.png")
        try:
            r = run_backtest(
                stock_symbol,
                key,
                start_date,
                end_date,
                cash=initial_cash,
                plot_path=plot_path,
                verbose=True,
                stop_loss_pct=args.stop_loss,
            )
        except Exception as exc:
            print(f"{name} 回测失败: {exc}")
            continue

        print(f"\n--- {name} 回测结果 ---")
        print(f"最终账户价值: {r['final_value']:.2f}")
        print(f"累计收益率: {r['return_pct']:.2f}%")
        print(f"买入持有: {r['buy_hold_pct']:.2f}%")
        print(f"最大回撤: {r['max_drawdown_pct']:.2f}%")
        print(f"年化夏普: {r['sharpe'] if r['sharpe'] is not None else '—'}")
        wr = "—" if r["win_rate_pct"] is None else f"{r['win_rate_pct']:.1f}%"
        print(f"胜率: {wr} · {r['round_trips']} 轮")
        if r.get("warning"):
            print(f"提示: {r['warning']}")
        if plot_path:
            print(f"回测图表已保存至: {plot_path}")
        print("-" * 30)

    print("\n所有策略回测完成！")
    print(f"所有图表已保存在目录: {plots_dir}")


if __name__ == "__main__":
    main()
