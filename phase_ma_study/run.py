"""
对缓存全部（或限定）股票做涨跌阶段 + MA5/10/20/30 综合分析、出图、大屏。

用法（在 quant_trade 目录下）:
  .\\.venv\\Scripts\\python.exe -m phase_ma_study.run
  .\\.venv\\Scripts\\python.exe -m phase_ma_study.run --limit 30
  .\\.venv\\Scripts\\python.exe -m phase_ma_study.run --universe low20
  .\\.venv\\Scripts\\python.exe -m phase_ma_study.run --no-charts   # 只统计不出图
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# 保证可从项目根 import qt.*
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from qt.data import list_cached_symbols, load_cached_bars, load_universe  # noqa: E402

from .analyze import (  # noqa: E402
    horizontal_analyze,
    phases_to_frame,
    vertical_analyze,
    write_json,
)
from .build_static import build_static_dashboard  # noqa: E402
from .catalog import write_catalog  # noqa: E402
from .config import DEFAULT_OUTPUT, MIN_PHASE_DAYS, MIN_PHASE_PCT_FOR_CHART  # noqa: E402
from .dashboard import build_dashboard, write_live_dashboard  # noqa: E402
from .detect import detect_phases  # noqa: E402
from .plot_phase import plot_phase_chart  # noqa: E402


def _stock_name(symbol: str, name_map: dict[str, str]) -> str:
    return name_map.get(symbol) or ""


def _load_name_map() -> dict[str, str]:
    try:
        import json
        from qt.config import CACHE_DIR

        p = CACHE_DIR / "names.json"
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
    except Exception:
        pass
    return {}


def resolve_symbols(universe: str | None, limit: int | None) -> list[str]:
    cached = list_cached_symbols()
    if universe:
        members = load_universe(universe)
        want = {m["symbol"] for m in members}
        symbols = [s for s in cached if s in want]
    else:
        symbols = cached
    if limit and limit > 0:
        symbols = symbols[:limit]
    return symbols


def run(
    output: Path | None = None,
    universe: str | None = None,
    limit: int | None = None,
    min_days: int = MIN_PHASE_DAYS,
    min_pct_chart: float = MIN_PHASE_PCT_FOR_CHART,
    charts: bool = True,
    pad_bars: int = 20,
) -> Path:
    out_dir = Path(output or DEFAULT_OUTPUT)
    stocks_dir = out_dir / "stocks"
    reports_dir = out_dir / "reports"
    stocks_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    # 一开始就写入动态大屏壳，任务过程中持续刷新 catalog.json
    write_live_dashboard(out_dir, refresh_catalog=True)

    symbols = resolve_symbols(universe, limit)
    names = _load_name_map()
    print(f"待分析股票: {len(symbols)} 只 → 输出 {out_dir}")
    print(f"动态大屏: 请另开终端运行  python -m phase_ma_study.viewer  → http://127.0.0.1:8770/")

    all_phases = []
    stock_cards = []
    t0 = time.time()

    for i, symbol in enumerate(symbols, 1):
        df = load_cached_bars(symbol)
        if df is None or df.empty:
            print(f"[{i}/{len(symbols)}] {symbol} 无缓存，跳过")
            continue
        # 全历史
        phases = detect_phases(symbol, df, min_days=min_days)
        name = _stock_name(symbol, names)
        stock_dir = stocks_dir / symbol
        stock_dir.mkdir(parents=True, exist_ok=True)

        horiz = horizontal_analyze(symbol, phases)
        # 方便大屏显示名称
        horiz["name"] = name
        write_json(stock_dir / "phases.json", [p.to_dict() for p in phases])
        write_json(stock_dir / "horizontal.json", horiz)

        images = []
        if charts:
            rise_n = fall_n = 0
            for p in phases:
                if abs(p.ret_pct) < min_pct_chart:
                    continue
                if p.kind == "rise":
                    rise_n += 1
                    seq = rise_n
                else:
                    fall_n += 1
                    seq = fall_n
                fname = f"{p.kind}_{seq:03d}_{p.start}_{p.end}.png"
                fpath = stock_dir / fname
                try:
                    plot_phase_chart(symbol, name, df, p, fpath, pad_bars=pad_bars)
                    rel = str(fpath.relative_to(out_dir)).replace("\\", "/")
                    images.append(
                        {
                            "kind": p.kind,
                            "path": rel,
                            "caption": (
                                f"{'升' if p.kind == 'rise' else '降'} "
                                f"{p.start}~{p.end}  {p.days}日  {p.ret_pct:+.1f}%"
                            ),
                        }
                    )
                except Exception as exc:
                    print(f"  出图失败 {symbol} {fname}: {exc}")

        all_phases.extend(phases)
        stock_cards.append(
            {
                "symbol": symbol,
                "name": name,
                "summary": horiz.get("summary") or "",
                "images": images,
            }
        )
        if i % 20 == 0 or i == len(symbols):
            elapsed = time.time() - t0
            print(
                f"[{i}/{len(symbols)}] {symbol} 阶段{len(phases)} 图{len(images)} "
                f"累计阶段{len(all_phases)} ({elapsed:.1f}s)"
            )
            # 增量刷新目录索引，动态大屏立刻能看到新图
            try:
                write_catalog(out_dir)
            except Exception as exc:
                print(f"  catalog 刷新失败: {exc}")
    # 纵向
    vertical = vertical_analyze(all_phases)
    write_json(reports_dir / "vertical.json", vertical)
    # 全量阶段表
    frame = phases_to_frame(all_phases)
    if not frame.empty:
        frame.to_csv(reports_dir / "all_phases.csv", index=False, encoding="utf-8-sig")

    # 公式摘要 markdown
    md_lines = ["# 涨跌阶段拟合摘要", "", "## 纵向（跨股）", ""]
    for line in vertical.get("narrative") or []:
        md_lines.append(f"- {line}")
    md_lines += ["", "## 单股横向摘要（节选）", ""]
    for c in stock_cards[:50]:
        md_lines.append(f"- **{c['symbol']}** {c.get('name') or ''}: {c.get('summary') or '—'}")
    (reports_dir / "formulas.md").write_text("\n".join(md_lines), encoding="utf-8")

    dash = build_static_dashboard(out_dir)
    print(f"完成。可双击打开: {dash}")
    print(f"报告: {reports_dir}")
    print("便携打包: python -m phase_ma_study.pack_portable")
    return dash


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="缓存股票涨跌阶段 + MA 综合分析")
    ap.add_argument("--output", type=str, default=None, help="输出目录")
    ap.add_argument("--universe", type=str, default=None, help="股票池: demo/low20/hs300/zz500/sz50")
    ap.add_argument("--limit", type=int, default=None, help="最多处理只数（调试用）")
    ap.add_argument("--min-days", type=int, default=MIN_PHASE_DAYS, help="最短阶段交易日")
    ap.add_argument(
        "--min-pct-chart",
        type=float,
        default=MIN_PHASE_PCT_FOR_CHART,
        help="出图最小涨跌幅绝对值%",
    )
    ap.add_argument("--no-charts", action="store_true", help="只做统计与 JSON，不出 PNG")
    ap.add_argument("--pad-bars", type=int, default=20, help="阶段前后各保留 K 线根数")
    args = ap.parse_args(argv)

    run(
        output=Path(args.output) if args.output else None,
        universe=args.universe,
        limit=args.limit,
        min_days=args.min_days,
        min_pct_chart=args.min_pct_chart,
        charts=not args.no_charts,
        pad_bars=args.pad_bars,
    )


if __name__ == "__main__":
    main()
