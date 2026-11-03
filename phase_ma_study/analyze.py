"""横向（单股多阶段）与纵向（跨股同阶段）综合拟合。"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .detect import Phase


def _safe_polyfit(x: np.ndarray, y: np.ndarray, deg: int) -> dict[str, Any]:
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    if len(x) < deg + 2:
        return {"ok": False, "n": int(len(x))}
    coefs = np.polyfit(x, y, deg)
    yhat = np.polyval(coefs, x)
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2)) or 1.0
    return {
        "ok": True,
        "n": int(len(x)),
        "degree": deg,
        "coefs": [float(c) for c in coefs],
        "r2": float(1.0 - ss_res / ss_tot),
        "formula": _formula_str(coefs, "x"),
    }


def _formula_str(coefs: np.ndarray | list[float], var: str = "x") -> str:
    parts = []
    deg = len(coefs) - 1
    for i, c in enumerate(coefs):
        p = deg - i
        c = float(c)
        if abs(c) < 1e-12:
            continue
        if p == 0:
            parts.append(f"{c:+.6g}")
        elif p == 1:
            parts.append(f"{c:+.6g}*{var}")
        else:
            parts.append(f"{c:+.6g}*{var}^{p}")
    return " ".join(parts) if parts else "0"


def horizontal_analyze(symbol: str, phases: list[Phase]) -> dict[str, Any]:
    """单股：上升/下降阶段之间的规律（天数↔收益、斜率↔回撤等）。"""
    rises = [p for p in phases if p.kind == "rise"]
    falls = [p for p in phases if p.kind == "fall"]

    def pack(ps: list[Phase], label: str) -> dict[str, Any]:
        if not ps:
            return {"label": label, "count": 0}
        days = np.array([p.days for p in ps], dtype=float)
        rets = np.array([p.ret_pct for p in ps], dtype=float)
        slopes = np.array([p.lin_b for p in ps], dtype=float)
        dds = np.array([p.max_dd_pct for p in ps], dtype=float)
        ma20s = np.array([p.ma20_slope for p in ps], dtype=float)
        return {
            "label": label,
            "count": len(ps),
            "ret_mean": float(np.nanmean(rets)),
            "ret_median": float(np.nanmedian(rets)),
            "days_mean": float(np.nanmean(days)),
            "days_median": float(np.nanmedian(days)),
            "lin_b_mean": float(np.nanmean(slopes)),
            "max_dd_mean": float(np.nanmean(dds)),
            # 天数 → 收益
            "fit_days_to_ret": _safe_polyfit(days, rets, 1),
            # 对数收益日斜率 → 总收益
            "fit_linb_to_ret": _safe_polyfit(slopes, rets, 1),
            # MA20 斜率 → 收益
            "fit_ma20_to_ret": _safe_polyfit(ma20s, rets, 1),
            # 天数 → 回撤
            "fit_days_to_dd": _safe_polyfit(days, dds, 1),
            "phases": [
                {
                    "start": p.start,
                    "end": p.end,
                    "days": p.days,
                    "ret_pct": round(p.ret_pct, 3),
                    "lin_b": round(p.lin_b, 6) if np.isfinite(p.lin_b) else None,
                    "lin_r2": round(p.lin_r2, 4) if np.isfinite(p.lin_r2) else None,
                    "formula_lin": (
                        f"ln(P) = {p.lin_a:.6g} + {p.lin_b:.6g}*t"
                        if np.isfinite(p.lin_a) and np.isfinite(p.lin_b)
                        else None
                    ),
                    "formula_quad": (
                        f"ln(P) = {p.quad_c0:.6g} + {p.quad_c1:.6g}*t + {p.quad_c2:.6g}*t^2"
                        if np.isfinite(p.quad_c0)
                        else None
                    ),
                }
                for p in ps
            ],
        }

    return {
        "symbol": symbol,
        "n_phases": len(phases),
        "rise": pack(rises, "rise"),
        "fall": pack(falls, "fall"),
        "summary": _horizontal_summary(rises, falls),
    }


def _horizontal_summary(rises: list[Phase], falls: list[Phase]) -> str:
    lines = []
    if rises:
        rm = float(np.nanmean([p.ret_pct for p in rises]))
        dm = float(np.nanmean([p.days for p in rises]))
        lines.append(f"上升阶段 {len(rises)} 段，平均持续 {dm:.1f} 日，平均涨幅 {rm:.2f}%")
    if falls:
        rm = float(np.nanmean([p.ret_pct for p in falls]))
        dm = float(np.nanmean([p.days for p in falls]))
        lines.append(f"下降阶段 {len(falls)} 段，平均持续 {dm:.1f} 日，平均跌幅 {rm:.2f}%")
    return "；".join(lines) if lines else "无有效阶段"


def vertical_analyze(all_phases: list[Phase]) -> dict[str, Any]:
    """跨股：同类阶段参数分布与通用拟合公式。"""
    by_kind: dict[str, list[Phase]] = defaultdict(list)
    for p in all_phases:
        by_kind[p.kind].append(p)

    out: dict[str, Any] = {"n_total": len(all_phases), "by_kind": {}}
    for kind, ps in by_kind.items():
        days = np.array([p.days for p in ps], dtype=float)
        rets = np.array([p.ret_pct for p in ps], dtype=float)
        slopes = np.array([p.lin_b for p in ps], dtype=float)
        ma5 = np.array([p.ma5_slope for p in ps], dtype=float)
        ma10 = np.array([p.ma10_slope for p in ps], dtype=float)
        ma20 = np.array([p.ma20_slope for p in ps], dtype=float)
        ma30 = np.array([p.ma30_slope for p in ps], dtype=float)
        # 分位统计
        def qstats(a: np.ndarray) -> dict:
            a = a[np.isfinite(a)]
            if len(a) == 0:
                return {}
            qs = np.nanpercentile(a, [10, 25, 50, 75, 90])
            return {
                "mean": float(np.mean(a)),
                "std": float(np.std(a)),
                "p10": float(qs[0]),
                "p25": float(qs[1]),
                "p50": float(qs[2]),
                "p75": float(qs[3]),
                "p90": float(qs[4]),
            }

        block = {
            "count": len(ps),
            "n_symbols": len({p.symbol for p in ps}),
            "ret": qstats(rets),
            "days": qstats(days),
            "lin_b": qstats(slopes),
            "ma5_slope": qstats(ma5),
            "ma10_slope": qstats(ma10),
            "ma20_slope": qstats(ma20),
            "ma30_slope": qstats(ma30),
            # 通用公式：天数 → 收益
            "universal_days_to_ret": _safe_polyfit(days, rets, 1),
            "universal_days_to_ret_quad": _safe_polyfit(days, rets, 2),
            # MA20 日斜率 → 阶段收益
            "universal_ma20_to_ret": _safe_polyfit(ma20, rets, 1),
            # 对数价格日斜率 → 收益
            "universal_linb_to_ret": _safe_polyfit(slopes, rets, 1),
        }
        out["by_kind"][kind] = block

    out["narrative"] = _vertical_narrative(out)
    return out


def _vertical_narrative(vert: dict) -> list[str]:
    lines = []
    for kind, b in (vert.get("by_kind") or {}).items():
        name = "上升" if kind == "rise" else "下降" if kind == "fall" else kind
        ret = b.get("ret") or {}
        days = b.get("days") or {}
        fit = b.get("universal_days_to_ret") or {}
        p50 = ret.get("p50", float("nan"))
        p25 = ret.get("p25", float("nan"))
        p75 = ret.get("p75", float("nan"))
        d50 = days.get("p50", float("nan"))
        lines.append(
            f"【{name}】共 {b.get('count')} 段、覆盖 {b.get('n_symbols')} 只股票；"
            f"收益中位 {p50:.2f}%（P25~P75: {p25:.2f}~{p75:.2f}），"
            f"持续中位 {d50:.1f} 日。"
        )
        if fit.get("ok"):
            lines.append(
                f"  通用线性：ret_pct ≈ {fit.get('formula')} （R²={fit.get('r2'):.3f}，n={fit.get('n')}，x=天数）"
            )
        fit2 = b.get("universal_ma20_to_ret") or {}
        if fit2.get("ok"):
            lines.append(
                f"  MA20斜率→收益：ret_pct ≈ {fit2.get('formula')} （R²={fit2.get('r2'):.3f}，x=ma20_slope）"
            )
    return lines


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def phases_to_frame(phases: list[Phase]) -> pd.DataFrame:
    if not phases:
        return pd.DataFrame()
    return pd.DataFrame([p.to_dict() for p in phases])
