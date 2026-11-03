"""
上升/下降阶段共性与指标相关分析。

从日线缓存补齐量价与常用技术指标，按阶段起/中/末提取特征，
计算与收益、与升/降类别的相关度，并给出可操作买卖点阈值。

用法:
  python -m phase_ma_study.correlate
  python -m phase_ma_study.correlate --limit-symbols 200   # 快速试跑
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from qt.data import load_cached_bars  # noqa: E402
from qt.indicators import enrich  # noqa: E402
from qt.sectors import load_sectors, lookup_sectors  # noqa: E402

from .config import DEFAULT_OUTPUT  # noqa: E402

# 参与相关分析的数值特征（阶段级）
FEATURE_COLS = [
    "days",
    "open_px",
    "avg_vol",
    "avg_amount",
    "avg_turnover",
    "vol_ratio_start",
    "vol_ratio_mean",
    "vol_ratio_end",
    "vol_surge",  # 阶段均量 / 前60日均量
    "amount_surge",
    "rsi_start",
    "rsi_mean",
    "rsi_end",
    "macd_hist_start",
    "macd_hist_mean",
    "macd_hist_end",
    "adx_mean",
    "bb_pct_b_start",
    "bb_pct_b_mean",
    "bb_pct_b_end",
    "kdj_j_start",
    "kdj_j_end",
    "ma5_slope",
    "ma10_slope",
    "ma20_slope",
    "ma30_slope",
    "ma_stack",  # 5>10>20>30 = 2; 部分多头=1; 空头=-1/-2
    "px_vs_ma5",
    "px_vs_ma10",
    "px_vs_ma20",
    "px_vs_ma30",
    "lin_b",
    "lin_r2",
    "atr_pct_mean",
]


def _sym(x: Any) -> str:
    s = str(x).strip()
    if s.isdigit():
        return s.zfill(6)
    return s


def _safe_mean(s: pd.Series) -> float:
    v = pd.to_numeric(s, errors="coerce")
    if v.notna().sum() == 0:
        return float("nan")
    return float(v.mean())


def _ma_stack_score(row: pd.Series) -> float:
    m5, m10, m20, m30 = row.get("sma5"), row.get("sma10"), row.get("sma20"), row.get("sma60")
    # 用 sma60 近似 30 日外的中长线；若无 ma30 列则用 sma20/sma60
    vals = [m5, m10, m20, m30]
    if any(pd.isna(v) for v in vals):
        return float("nan")
    score = 0.0
    if m5 > m10:
        score += 1
    else:
        score -= 1
    if m10 > m20:
        score += 1
    else:
        score -= 1
    if m20 > m30:
        score += 1
    else:
        score -= 1
    return score


def _pct_above(close: float, ma: float) -> float:
    if pd.isna(close) or pd.isna(ma) or ma == 0:
        return float("nan")
    return (close / ma - 1.0) * 100.0


def extract_phase_features(df: pd.DataFrame, i0: int, i1: int) -> dict[str, float]:
    """在已 enrich 的日线上提取阶段特征。"""
    n = len(df)
    i0 = max(0, min(int(i0), n - 1))
    i1 = max(i0, min(int(i1), n - 1))
    seg = df.iloc[i0 : i1 + 1]
    start = df.iloc[i0]
    end = df.iloc[i1]

    pre0 = max(0, i0 - 60)
    pre = df.iloc[pre0:i0] if i0 > pre0 else df.iloc[0:0]
    pre_vol = float(pre["volume"].mean()) if len(pre) >= 10 else float("nan")
    pre_amt = float(pre["amount"].mean()) if len(pre) >= 10 and "amount" in pre else float("nan")

    avg_vol = float(seg["volume"].mean())
    avg_amount = float(seg["amount"].mean()) if "amount" in seg else float("nan")
    avg_turnover = float(seg["turnover"].mean()) if "turnover" in seg else float("nan")

    close = float(start["close"])
    out = {
        "avg_amount": avg_amount,
        "avg_turnover": avg_turnover,
        "vol_ratio_start": float(start.get("vol_ratio", np.nan)),
        "vol_ratio_mean": _safe_mean(seg["vol_ratio"]) if "vol_ratio" in seg else float("nan"),
        "vol_ratio_end": float(end.get("vol_ratio", np.nan)),
        "vol_surge": (avg_vol / pre_vol) if np.isfinite(pre_vol) and pre_vol > 0 else float("nan"),
        "amount_surge": (
            (avg_amount / pre_amt) if np.isfinite(pre_amt) and pre_amt > 0 else float("nan")
        ),
        "rsi_start": float(start.get("rsi14", np.nan)),
        "rsi_mean": _safe_mean(seg["rsi14"]) if "rsi14" in seg else float("nan"),
        "rsi_end": float(end.get("rsi14", np.nan)),
        "macd_hist_start": float(start.get("macd_hist", np.nan)),
        "macd_hist_mean": _safe_mean(seg["macd_hist"]) if "macd_hist" in seg else float("nan"),
        "macd_hist_end": float(end.get("macd_hist", np.nan)),
        "adx_mean": _safe_mean(seg["adx14"]) if "adx14" in seg else float("nan"),
        "bb_pct_b_start": float(start.get("bb_pct_b", np.nan)),
        "bb_pct_b_mean": _safe_mean(seg["bb_pct_b"]) if "bb_pct_b" in seg else float("nan"),
        "bb_pct_b_end": float(end.get("bb_pct_b", np.nan)),
        "kdj_j_start": float(start.get("kdj_j", np.nan)),
        "kdj_j_end": float(end.get("kdj_j", np.nan)),
        "ma_stack": _ma_stack_score(start),
        "px_vs_ma5": _pct_above(close, float(start.get("sma5", np.nan))),
        "px_vs_ma10": _pct_above(close, float(start.get("sma10", np.nan))),
        "px_vs_ma20": _pct_above(close, float(start.get("sma20", np.nan))),
        "px_vs_ma30": _pct_above(close, float(start.get("sma60", np.nan))),  # 用60近似中长线
        "atr_pct_mean": float("nan"),
    }
    if "atr14" in seg.columns:
        atr_pct = seg["atr14"] / seg["close"].replace(0, np.nan) * 100.0
        out["atr_pct_mean"] = _safe_mean(atr_pct)
    return out


def build_feature_frame(
    phases: pd.DataFrame,
    limit_symbols: int | None = None,
) -> pd.DataFrame:
    phases = phases.copy()
    phases["symbol"] = phases["symbol"].map(_sym)
    symbols = sorted(phases["symbol"].unique())
    if limit_symbols and limit_symbols > 0:
        symbols = symbols[:limit_symbols]
        phases = phases[phases["symbol"].isin(symbols)]

    sectors = load_sectors()
    rows: list[dict[str, Any]] = []
    t0 = time.time()
    for i, sym in enumerate(symbols, 1):
        try:
            raw = load_cached_bars(sym)
        except Exception:
            continue
        if raw is None or raw.empty or len(raw) < 80:
            continue
        try:
            df = enrich(raw)
        except Exception:
            continue
        # 补 sma30 供堆栈用（enrich 已有 sma5/10/20/60）
        if "sma30" not in df.columns:
            df["sma30"] = df["close"].rolling(30, min_periods=30).mean()

        industry, concepts = lookup_sectors(sym, sectors)
        sub = phases[phases["symbol"] == sym]
        for _, ph in sub.iterrows():
            try:
                feat = extract_phase_features(df, int(ph["i0"]), int(ph["i1"]))
            except Exception:
                continue
            # 用真实 ma30 重算 stack / px_vs
            i0 = max(0, min(int(ph["i0"]), len(df) - 1))
            start = df.iloc[i0]
            m5, m10, m20, m30 = start.get("sma5"), start.get("sma10"), start.get("sma20"), start.get("sma30")
            if all(pd.notna(v) for v in (m5, m10, m20, m30)):
                score = 0.0
                score += 1 if m5 > m10 else -1
                score += 1 if m10 > m20 else -1
                score += 1 if m20 > m30 else -1
                feat["ma_stack"] = score
                feat["px_vs_ma30"] = _pct_above(float(start["close"]), float(m30))

            row = {
                "symbol": sym,
                "kind": ph["kind"],
                "start": ph["start"],
                "end": ph["end"],
                "days": float(ph["days"]),
                "open_px": float(ph["open_px"]),
                "ret_pct": float(ph["ret_pct"]),
                "max_dd_pct": float(ph["max_dd_pct"]),
                "avg_vol": float(ph["avg_vol"]),
                "ma5_slope": float(ph["ma5_slope"]),
                "ma10_slope": float(ph["ma10_slope"]),
                "ma20_slope": float(ph["ma20_slope"]),
                "ma30_slope": float(ph["ma30_slope"]) if pd.notna(ph.get("ma30_slope")) else float("nan"),
                "lin_b": float(ph["lin_b"]),
                "lin_r2": float(ph["lin_r2"]),
                "industry": industry or "未分类",
                "n_concepts": len(concepts or []),
                **feat,
            }
            rows.append(row)

        if i % 100 == 0 or i == len(symbols):
            elapsed = time.time() - t0
            print(f"  [{i}/{len(symbols)}] features={len(rows)}  {elapsed:.0f}s", flush=True)

    return pd.DataFrame(rows)


def _corr_with(df: pd.DataFrame, target: str, cols: list[str]) -> list[dict[str, Any]]:
    out = []
    y = pd.to_numeric(df[target], errors="coerce")
    for c in cols:
        if c not in df.columns:
            continue
        x = pd.to_numeric(df[c], errors="coerce")
        mask = x.notna() & y.notna()
        n = int(mask.sum())
        if n < 200:
            continue
        r = float(x[mask].corr(y[mask]))
        if not np.isfinite(r):
            continue
        out.append({"feature": c, "corr": round(r, 4), "n": n, "abs": abs(r)})
    out.sort(key=lambda d: -d["abs"])
    return out


def _kind_effect(df: pd.DataFrame, cols: list[str]) -> list[dict[str, Any]]:
    """上升 vs 下降：均值差 + 点二列相关（kind 编码 1/-1）。"""
    rise = df[df["kind"] == "rise"]
    fall = df[df["kind"] == "fall"]
    kind_code = df["kind"].map({"rise": 1.0, "fall": -1.0})
    out = []
    for c in cols:
        if c not in df.columns:
            continue
        xr = pd.to_numeric(rise[c], errors="coerce")
        xf = pd.to_numeric(fall[c], errors="coerce")
        x = pd.to_numeric(df[c], errors="coerce")
        mr, mf = float(xr.mean()), float(xf.mean())
        if not np.isfinite(mr) or not np.isfinite(mf):
            continue
        mask = x.notna() & kind_code.notna()
        n = int(mask.sum())
        if n < 200:
            continue
        r = float(x[mask].corr(kind_code[mask]))
        # 标准化均值差（pooled std）
        pooled = float(np.nanstd(np.concatenate([xr.dropna().to_numpy(), xf.dropna().to_numpy()])))
        d = (mr - mf) / pooled if pooled and np.isfinite(pooled) else float("nan")
        out.append(
            {
                "feature": c,
                "rise_mean": round(mr, 4),
                "fall_mean": round(mf, 4),
                "cohen_d": round(float(d), 4) if np.isfinite(d) else None,
                "corr_with_rise": round(r, 4) if np.isfinite(r) else None,
                "n": n,
            }
        )
    out.sort(key=lambda d: -(abs(d["corr_with_rise"] or 0)))
    return out


def _quantile_edge(
    df: pd.DataFrame,
    feature: str,
    target: str = "ret_pct",
    q_low: float = 0.2,
    q_high: float = 0.8,
) -> dict[str, Any] | None:
    x = pd.to_numeric(df[feature], errors="coerce")
    y = pd.to_numeric(df[target], errors="coerce")
    mask = x.notna() & y.notna()
    if mask.sum() < 500:
        return None
    x, y = x[mask], y[mask]
    lo, hi = float(x.quantile(q_low)), float(x.quantile(q_high))
    low_ret = float(y[x <= lo].mean())
    high_ret = float(y[x >= hi].mean())
    mid_ret = float(y[(x > lo) & (x < hi)].mean())
    return {
        "feature": feature,
        "q20": round(lo, 4),
        "q80": round(hi, 4),
        "ret_when_low": round(low_ret, 3),
        "ret_when_mid": round(mid_ret, 3),
        "ret_when_high": round(high_ret, 3),
        "edge_high_minus_low": round(high_ret - low_ret, 3),
    }


def derive_rules(feat: pd.DataFrame, kind_eff: list[dict], rise_corr: list[dict], fall_corr: list[dict]) -> dict[str, Any]:
    """基于相关与分位差提炼买卖点叙事规则（非实盘保证）。"""
    buy: list[str] = []
    sell: list[str] = []
    notes: list[str] = []

    # 升跌区分度最高的特征
    top_disc = [x for x in kind_eff if x.get("corr_with_rise") is not None][:8]
    for x in top_disc:
        c = x["feature"]
        if (x["corr_with_rise"] or 0) > 0.15:
            buy.append(
                f"买入参考：{c} 偏高更像上升段（升均 {x['rise_mean']} / 降均 {x['fall_mean']}，"
                f"与上升相关 r={x['corr_with_rise']}，效应量 d={x['cohen_d']}）"
            )
        elif (x["corr_with_rise"] or 0) < -0.15:
            sell.append(
                f"卖出/回避：{c} 偏高更像下降段（升均 {x['rise_mean']} / 降均 {x['fall_mean']}，"
                f"r={x['corr_with_rise']}）"
            )

    # 上升段内：高相关 → 幅度预期
    for x in rise_corr[:6]:
        c, r = x["feature"], x["corr"]
        if abs(r) < 0.15:
            continue
        edge = _quantile_edge(feat[feat["kind"] == "rise"], c)
        if not edge:
            continue
        if r > 0:
            buy.append(
                f"上升段加仓强度：{c} 越高，阶段涨幅越大（r={r}）；"
                f"高分位(≥{edge['q80']})均涨 {edge['ret_when_high']}% vs 低分位 {edge['ret_when_low']}%"
            )
        else:
            buy.append(
                f"上升段：{c} 越低涨幅越大（r={r}）；"
                f"低分位(≤{edge['q20']})均涨 {edge['ret_when_low']}% vs 高分位 {edge['ret_when_high']}%"
            )

    for x in fall_corr[:6]:
        c, r = x["feature"], x["corr"]
        if abs(r) < 0.15:
            continue
        edge = _quantile_edge(feat[feat["kind"] == "fall"], c)
        if not edge:
            continue
        if r < 0:
            sell.append(
                f"下降段：{c} 越高跌得越狠（r={r}）；"
                f"高分位均跌 {edge['ret_when_high']}% vs 低分位 {edge['ret_when_low']}%"
            )
        else:
            sell.append(
                f"下降段：{c} 越低跌幅越大（r={r}）；"
                f"低分位均跌 {edge['ret_when_low']}% vs 高分位 {edge['ret_when_high']}%"
            )

    notes.append(
        "相关度为皮尔逊 r；|r|<0.15 视为弱相关，0.15~0.3 弱~中，0.3~0.5 中等，>0.5 较强。"
        "阶段由收盘价相对 MA20 + MA5/MA20 划分，特征含起点与段内均值；非未来保证。"
    )
    notes.append(
        "缓存日线无「主力资金」字段，本报告用成交额、量比、量能放大(vol_surge/amount_surge)、换手率作资金活跃度代理。"
    )
    return {"buy_rules": buy[:12], "sell_rules": sell[:12], "notes": notes}


def industry_stats(feat: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for ind, g in feat.groupby("industry"):
        if len(g) < 80 or not ind or ind == "未分类":
            continue
        rise = g[g["kind"] == "rise"]
        fall = g[g["kind"] == "fall"]
        rows.append(
            {
                "industry": ind,
                "n": int(len(g)),
                "rise_share": round(len(rise) / len(g), 3),
                "rise_ret_med": round(float(rise["ret_pct"].median()), 3) if len(rise) else None,
                "fall_ret_med": round(float(fall["ret_pct"].median()), 3) if len(fall) else None,
                "days_med": round(float(g["days"].median()), 1),
            }
        )
    rows.sort(key=lambda d: -(d["rise_ret_med"] or 0))
    return rows[:40]


def summarize_kind(feat: pd.DataFrame, kind: str) -> dict[str, Any]:
    g = feat[feat["kind"] == kind]
    def med(c: str) -> float | None:
        if c not in g:
            return None
        v = float(pd.to_numeric(g[c], errors="coerce").median())
        return round(v, 4) if np.isfinite(v) else None

    return {
        "n": int(len(g)),
        "ret_med": med("ret_pct"),
        "days_med": med("days"),
        "vol_ratio_mean_med": med("vol_ratio_mean"),
        "vol_surge_med": med("vol_surge"),
        "amount_surge_med": med("amount_surge"),
        "rsi_mean_med": med("rsi_mean"),
        "macd_hist_mean_med": med("macd_hist_mean"),
        "adx_mean_med": med("adx_mean"),
        "ma_stack_med": med("ma_stack"),
        "ma20_slope_med": med("ma20_slope"),
        "bb_pct_b_mean_med": med("bb_pct_b_mean"),
        "turnover_med": med("avg_turnover"),
    }


def build_report_html(report: dict[str, Any], out_path: Path) -> Path:
    def tbl(rows: list[dict], cols: list[tuple[str, str]]) -> str:
        if not rows:
            return "<p class='muted'>无数据</p>"
        th = "".join(f"<th>{h}</th>" for _, h in cols)
        body = []
        for r in rows:
            tds = "".join(f"<td>{r.get(k, '')}</td>" for k, _ in cols)
            body.append(f"<tr>{tds}</tr>")
        return f"<table><thead><tr>{th}</tr></thead><tbody>{''.join(body)}</tbody></table>"

    rise_c = report["corr_ret"]["rise"][:15]
    fall_c = report["corr_ret"]["fall"][:15]
    disc = report["kind_discrimination"][:15]
    buy = "".join(f"<li>{x}</li>" for x in report["rules"]["buy_rules"])
    sell = "".join(f"<li>{x}</li>" for x in report["rules"]["sell_rules"])
    notes = "".join(f"<li>{x}</li>" for x in report["rules"]["notes"])
    ind = report.get("industry") or []

    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<title>升跌阶段指标相关与买卖点</title>
<style>
body{{font-family:"Segoe UI","Microsoft YaHei",sans-serif;background:#0e100c;color:#efe7d6;margin:0;padding:24px;line-height:1.5}}
h1{{color:#e6ff4a;font-size:22px}} h2{{color:#e6ff4a;font-size:16px;margin-top:28px}}
.muted{{color:#8b8473;font-size:13px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
.card{{background:#161910;border:1px solid #2c3224;border-radius:8px;padding:14px 16px}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
th,td{{border-bottom:1px solid #2c3224;padding:6px 8px;text-align:left}}
th{{color:#8b8473;font-weight:600}}
ul{{padding-left:18px;font-size:13px;color:#cfc7b6}}
.stat{{display:inline-block;margin-right:18px}}
.stat b{{color:#e6ff4a}}
@media(max-width:900px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body>
<h1>升跌阶段共性 · 指标相关 · 买卖点</h1>
<p class="muted">样本 {report['meta']['n_phases']} 段 / {report['meta']['n_symbols']} 股 ·
生成于 {report['meta']['built_at']} · 直接双击本 HTML 即可查看</p>
<div class="card">
  <span class="stat">上升中位涨幅 <b>{report['summary']['rise']['ret_med']}%</b></span>
  <span class="stat">下降中位跌幅 <b>{report['summary']['fall']['ret_med']}%</b></span>
  <span class="stat">上升量能放大中位 <b>{report['summary']['rise']['vol_surge_med']}</b></span>
  <span class="stat">下降量能放大中位 <b>{report['summary']['fall']['vol_surge_med']}</b></span>
</div>

<h2>买卖点规则（数据驱动）</h2>
<div class="grid">
  <div class="card"><h2 style="margin-top:0">买入 / 持有偏多</h2><ul>{buy}</ul></div>
  <div class="card"><h2 style="margin-top:0">卖出 / 回避偏空</h2><ul>{sell}</ul></div>
</div>
<ul class="muted">{notes}</ul>

<h2>升 vs 降：哪些指标能区分趋势方向</h2>
<div class="card">
{tbl(disc, [
  ("feature","指标"),("rise_mean","上升均值"),("fall_mean","下降均值"),
  ("cohen_d","效应量d"),("corr_with_rise","与上升相关r"),("n","n")
])}
</div>

<div class="grid">
  <div class="card">
    <h2 style="margin-top:0">上升段内：指标 ↔ 涨幅相关</h2>
    {tbl(rise_c, [("feature","指标"),("corr","r"),("n","n")])}
  </div>
  <div class="card">
    <h2 style="margin-top:0">下降段内：指标 ↔ 跌幅相关</h2>
    {tbl(fall_c, [("feature","指标"),("corr","r"),("n","n")])}
  </div>
</div>

<h2>行业（板块）差异 Top</h2>
<div class="card">
{tbl(ind[:25], [
  ("industry","行业"),("n","阶段数"),("rise_share","上升占比"),
  ("rise_ret_med","升中位%"),("fall_ret_med","降中位%"),("days_med","持续日中位")
])}
</div>

<h2>上升 / 下降阶段画像（中位数）</h2>
<div class="grid">
  <div class="card"><pre style="white-space:pre-wrap;font-size:12px">{json.dumps(report['summary']['rise'], ensure_ascii=False, indent=2)}</pre></div>
  <div class="card"><pre style="white-space:pre-wrap;font-size:12px">{json.dumps(report['summary']['fall'], ensure_ascii=False, indent=2)}</pre></div>
</div>
</body></html>"""
    out_path.write_text(html, encoding="utf-8")
    return out_path


def run(output: Path | None = None, limit_symbols: int | None = None) -> dict[str, Any]:
    out_dir = Path(output or DEFAULT_OUTPUT)
    report_dir = out_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    phases_path = report_dir / "all_phases.csv"
    if not phases_path.exists():
        raise FileNotFoundError(f"缺少 {phases_path}，请先跑 phase_ma_study.run")

    print("读取 all_phases.csv …")
    phases = pd.read_csv(phases_path)
    print(f"阶段 {len(phases)} 行，开始补齐指标特征…")
    feat = build_feature_frame(phases, limit_symbols=limit_symbols)
    feat_path = report_dir / "phase_features.csv"
    feat.to_csv(feat_path, index=False, encoding="utf-8-sig")
    print(f"特征表已写 {feat_path}  shape={feat.shape}")

    cols = [c for c in FEATURE_COLS if c in feat.columns]
    rise = feat[feat["kind"] == "rise"]
    fall = feat[feat["kind"] == "fall"]

    report: dict[str, Any] = {
        "meta": {
            "n_phases": int(len(feat)),
            "n_symbols": int(feat["symbol"].nunique()),
            "n_rise": int(len(rise)),
            "n_fall": int(len(fall)),
            "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "note_main_force": "无主力资金原始字段，已用量额/换手/量比代理",
        },
        "summary": {
            "rise": summarize_kind(feat, "rise"),
            "fall": summarize_kind(feat, "fall"),
        },
        "kind_discrimination": _kind_effect(feat, cols),
        "corr_ret": {
            "rise": _corr_with(rise, "ret_pct", cols),
            "fall": _corr_with(fall, "ret_pct", cols),
            "all": _corr_with(feat, "ret_pct", cols),
        },
        "quantile_edges_rise": [
            e
            for c in cols
            if (e := _quantile_edge(rise, c)) is not None and abs(e["edge_high_minus_low"]) >= 1.5
        ],
        "industry": industry_stats(feat),
    }
    report["quantile_edges_rise"].sort(key=lambda d: -abs(d["edge_high_minus_low"]))
    report["rules"] = derive_rules(
        feat,
        report["kind_discrimination"],
        report["corr_ret"]["rise"],
        report["corr_ret"]["fall"],
    )

    json_path = report_dir / "correlation_report.json"
    write_payload = {k: v for k, v in report.items()}
    json_path.write_text(json.dumps(write_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path = build_report_html(report, out_dir / "correlation.html")
    print(f"报告 JSON: {json_path}")
    print(f"报告 HTML: {html_path}")
    return report


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default=str(DEFAULT_OUTPUT))
    ap.add_argument("--limit-symbols", type=int, default=None)
    args = ap.parse_args(argv)
    run(Path(args.output), limit_symbols=args.limit_symbols)


if __name__ == "__main__":
    main()
