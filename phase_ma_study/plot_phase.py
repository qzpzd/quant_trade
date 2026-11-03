"""阶段 K 线 + MA5/10/20/30 出图（含前后上下文）。"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd

from .config import MA_PERIODS
from .detect import Phase, add_mas

# 中文字体兜底
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

MA_COLORS = {5: "#e6ff4a", 10: "#7aa2ff", 20: "#e4454a", 30: "#c98bdb"}


def plot_phase_chart(
    symbol: str,
    name: str,
    df: pd.DataFrame,
    phase: Phase,
    out_path: Path,
    pad_bars: int = 20,
) -> Path | None:
    """绘制阶段前后上下文 K 线 + 均线，高亮阶段区间。"""
    if df is None or df.empty:
        return None
    work = add_mas(df)
    i0 = max(0, phase.i0 - pad_bars)
    i1 = min(len(work) - 1, phase.i1 + pad_bars)
    seg = work.iloc[i0 : i1 + 1]
    if seg.empty:
        return None

    fig, (ax, axv) = plt.subplots(
        2, 1, figsize=(12, 7), sharex=True, gridspec_kw={"height_ratios": [3.2, 1]}
    )
    dates = seg.index.to_pydatetime() if hasattr(seg.index, "to_pydatetime") else list(seg.index)
    x = np.arange(len(seg))

    # K 线
    for i, (idx, row) in enumerate(seg.iterrows()):
        o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
        up = c >= o
        color = "#e4454a" if up else "#2ea574"
        ax.plot([i, i], [l, h], color=color, linewidth=0.8)
        body_lo, body_hi = min(o, c), max(o, c)
        ax.add_patch(
            Rectangle(
                (i - 0.35, body_lo),
                0.7,
                max(body_hi - body_lo, 1e-6),
                facecolor=color,
                edgecolor=color,
                linewidth=0.5,
            )
        )

    # 均线
    for p in MA_PERIODS:
        col = f"ma{p}"
        if col in seg:
            ax.plot(x, seg[col].to_numpy(), label=f"MA{p}", color=MA_COLORS[p], linewidth=1.2)

    # 阶段高亮
    local_a = phase.i0 - i0
    local_b = phase.i1 - i0
    ax.axvspan(local_a - 0.5, local_b + 0.5, color="#e6ff4a", alpha=0.12)
    # 拟合曲线（阶段内）
    if np.isfinite(phase.lin_a) and np.isfinite(phase.lin_b):
        t = np.arange(local_b - local_a + 1, dtype=float)
        fit_px = np.exp(phase.lin_a + phase.lin_b * t)
        ax.plot(
            np.arange(local_a, local_b + 1),
            fit_px,
            color="#efe7d6",
            linestyle="--",
            linewidth=1.4,
            label="ln拟合",
        )

    kind_cn = "上升" if phase.kind == "rise" else "下降"
    ax.set_title(
        f"{symbol} {name} · {kind_cn} {phase.start}~{phase.end} · "
        f"{phase.days}日 · 收益{phase.ret_pct:+.2f}% · R²={phase.lin_r2:.3f}"
        if np.isfinite(phase.lin_r2)
        else f"{symbol} {name} · {kind_cn} {phase.start}~{phase.end}"
    )
    ax.legend(loc="upper left", fontsize=8, ncol=5)
    ax.grid(True, alpha=0.25)
    ax.set_ylabel("价格")

    # 成交量
    if "volume" in seg:
        vols = seg["volume"].astype(float).to_numpy()
        colors = [
            "#e4454a" if float(seg.iloc[i]["close"]) >= float(seg.iloc[i]["open"]) else "#2ea574"
            for i in range(len(seg))
        ]
        axv.bar(x, vols, color=colors, width=0.7, alpha=0.7)
    axv.set_ylabel("量")
    axv.grid(True, alpha=0.2)

    # x 轴日期标签
    step = max(1, len(seg) // 8)
    ticks = list(range(0, len(seg), step))
    axv.set_xticks(ticks)
    labels = []
    for ti in ticks:
        d = seg.index[ti]
        labels.append(str(pd.Timestamp(d).date()))
    axv.set_xticklabels(labels, rotation=30, ha="right", fontsize=8)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path
