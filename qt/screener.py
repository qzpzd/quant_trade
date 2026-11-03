"""Conditional stock screener over an index universe."""

from __future__ import annotations

from qt.data import fundamentals_map, load_bars, load_spot, load_universe, stock_name
from qt.indicators import enrich, last_snapshot
from qt.selection import detect

SCREEN_FIELDS = [
    {"id": "rsi14", "label": "RSI(14)", "type": "number", "hint": "例如 < 30 超卖，> 70 超买"},
    {"id": "pct_chg", "label": "当日涨跌幅(%)", "type": "number"},
    {"id": "pct_5", "label": "5日涨跌幅(%)", "type": "number"},
    {"id": "pct_20", "label": "20日涨跌幅(%)", "type": "number"},
    {"id": "vol_ratio", "label": "量比(过去5日均量)", "type": "number", "hint": "当日量÷过去5日均量（不含当日）"},
    {"id": "bb_pct_b", "label": "布林 %B", "type": "number", "hint": "<0 跌破下轨，>1 升破上轨"},
    {"id": "adx14", "label": "ADX(14)", "type": "number"},
    {"id": "pe", "label": "市盈率(动态)", "type": "number"},
    {"id": "pb", "label": "市净率", "type": "number"},
    {"id": "turnover", "label": "换手率(%)", "type": "number"},
    {"id": "mv", "label": "总市值(元)", "type": "number"},
    {"id": "macd_cross", "label": "MACD 交叉", "type": "enum", "options": ["golden", "dead"]},
    {"id": "ma_align", "label": "均线排列", "type": "enum", "options": ["bull", "bear"]},
    {"id": "close_vs_sma20", "label": "收盘相对 MA20", "type": "enum", "options": ["above", "below"]},
    {"id": "rsi2", "label": "RSI(2)", "type": "number", "hint": "Connors：<10 超卖"},
    {"id": "st_dir", "label": "SuperTrend 方向", "type": "enum", "options": ["bull", "bear"]},
    {"id": "first_limit_up", "label": "底部首板涨停/大涨", "type": "enum", "options": ["yes"], "hint": "最近一根大涨（≥7%），启动前处于底部且此前无同级别大涨"},
    {"id": "bull_pullback", "label": "大阳线缩量回踩", "type": "enum", "options": ["yes"], "hint": "放量大阳线后连续缩量回踩至 MA10/MA20 附近"},
    {"id": "vol_breakout", "label": "底部放量启动", "type": "enum", "options": ["yes"], "hint": "历史低位 + 低量后突然放量"},
    {"id": "dist_sma20", "label": "距MA20(%)", "type": "number", "hint": "收盘相对 MA20 的偏离百分比，负值=在均线下方"},
    {"id": "roe", "label": "净资产收益率(%)", "type": "number"},
    {"id": "net_profit_yoy", "label": "净利润同比(%)", "type": "number"},
    {"id": "revenue_yoy", "label": "营收同比(%)", "type": "number"},
    {"id": "gross_margin", "label": "销售毛利率(%)", "type": "number"},
]

ENUM_FIELDS = (
    "macd_cross",
    "ma_align",
    "close_vs_sma20",
    "st_dir",
    "first_limit_up",
    "bull_pullback",
    "vol_breakout",
)
FIELD_LABEL = {f["id"]: f["label"] for f in SCREEN_FIELDS}
ENUM_LABEL = {
    "golden": "金叉",
    "dead": "死叉",
    "bull": "多头",
    "bear": "空头",
    "above": "上方",
    "below": "下方",
    "yes": "是",
    "no": "否",
}

OPS = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "=": lambda a, b: str(a) == str(b),
}


def _field_label(field: str) -> str:
    return FIELD_LABEL.get(field) or field


def _enum_label(value) -> str:
    key = str(value)
    return ENUM_LABEL.get(key, key)


def _to_float(raw):
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _tighten_lo(cur, val, inclusive):
    if cur is None:
        return (val, inclusive)
    cv, ci = cur
    if val > cv:
        return (val, inclusive)
    if val < cv:
        return cur
    return (cv, ci and inclusive)


def _tighten_hi(cur, val, inclusive):
    if cur is None:
        return (val, inclusive)
    cv, ci = cur
    if val < cv:
        return (val, inclusive)
    if val > cv:
        return cur
    return (cv, ci and inclusive)


def condition_conflicts(conditions: list[dict]) -> list[str]:
    """Human-readable reasons why AND-combined conditions cannot all be true."""
    reasons = []
    by_field: dict[str, list[dict]] = {}
    for cond in conditions or []:
        field = cond.get("field")
        if not field:
            continue
        by_field.setdefault(field, []).append(cond)

    for field, items in by_field.items():
        label = _field_label(field)
        if field in ENUM_FIELDS:
            equals = []
            for cond in items:
                raw = cond.get("value")
                if raw is None or str(raw).strip() == "":
                    continue
                op = cond.get("op") or "="
                if op != "=":
                    reasons.append(f"{label} 是分类字段，只能用「=」")
                    continue
                equals.append(str(raw))
            uniq = list(dict.fromkeys(equals))
            if len(uniq) > 1:
                shown = "、".join(_enum_label(v) for v in uniq)
                reasons.append(f"{label} 不能同时为 {shown}")
            continue

        lo = None
        hi = None
        eqs: list[float] = []
        for cond in items:
            op = cond.get("op") or ">"
            val = _to_float(cond.get("value"))
            if val is None:
                continue
            if op == ">":
                lo = _tighten_lo(lo, val, False)
            elif op == ">=":
                lo = _tighten_lo(lo, val, True)
            elif op == "<":
                hi = _tighten_hi(hi, val, False)
            elif op == "<=":
                hi = _tighten_hi(hi, val, True)
            elif op == "=":
                eqs.append(val)
        if len(set(eqs)) > 1:
            shown = "、".join(str(v) for v in dict.fromkeys(eqs))
            reasons.append(f"{label} 不能同时等于 {shown}")
            continue
        if eqs:
            v = eqs[0]
            if lo and (v < lo[0] or (v == lo[0] and not lo[1])):
                reasons.append(f"{label} 等于 {v} 与下界冲突")
            if hi and (v > hi[0] or (v == hi[0] and not hi[1])):
                reasons.append(f"{label} 等于 {v} 与上界冲突")
        if lo and hi:
            if lo[0] > hi[0] or (lo[0] == hi[0] and not (lo[1] and hi[1])):
                lo_s = f"{'≥' if lo[1] else '>'} {lo[0]}"
                hi_s = f"{'≤' if hi[1] else '<'} {hi[0]}"
                reasons.append(f"{label} 同时要求 {lo_s} 且 {hi_s}，没有交集")
    return reasons


def validate_conditions(conditions: list[dict]) -> None:
    missing = []
    for cond in conditions or []:
        if not str(cond.get("value") if cond.get("value") is not None else "").strip():
            missing.append(_field_label(cond.get("field")))
    if missing:
        raise RuntimeError("请填写条件阈值：" + "、".join(missing))
    reasons = condition_conflicts(conditions)
    if reasons:
        raise RuntimeError("条件冲突：" + "；".join(reasons))


def _tech_row(symbol: str) -> dict | None:
    try:
        df = load_bars(symbol, "20220101", None)
    except Exception:
        return None
    if df is None or df.empty or len(df) < 60:
        return None
    x = enrich(df)
    snap = last_snapshot(x)
    prev = x.iloc[-2]
    dif, dea = snap.get("macd_dif"), snap.get("macd_dea")
    pdif, pdea = float(prev["macd_dif"]), float(prev["macd_dea"])
    macd_cross = None
    if dif is not None and dea is not None:
        if pdif <= pdea and dif > dea:
            macd_cross = "golden"
        elif pdif >= pdea and dif < dea:
            macd_cross = "dead"
    sma5, sma20, sma60 = snap.get("sma5"), snap.get("sma20"), snap.get("sma60")
    ma_align = None
    if sma5 and sma20 and sma60:
        if sma5 > sma20 > sma60:
            ma_align = "bull"
        elif sma5 < sma20 < sma60:
            ma_align = "bear"
    close, sma20 = snap.get("close"), snap.get("sma20")
    close_vs_sma20 = None
    if close and sma20:
        close_vs_sma20 = "above" if close >= sma20 else "below"
    st = snap.get("st_dir")
    if st == 1 or st == 1.0:
        st_dir = "bull"
    elif st == -1 or st == -1.0:
        st_dir = "bear"
    else:
        st_dir = None
    snap["macd_cross"] = macd_cross
    snap["ma_align"] = ma_align
    snap["close_vs_sma20"] = close_vs_sma20
    snap["st_dir"] = st_dir
    close_v, sma20_v = snap.get("close"), snap.get("sma20")
    if close_v and sma20_v:
        snap["dist_sma20"] = (close_v - sma20_v) / sma20_v * 100
    try:
        snap.update(detect(x))
    except Exception:
        pass
    snap["symbol"] = symbol
    try:
        fund = fundamentals_map().get(symbol) or {}
        for key in ("roe", "net_profit_yoy", "revenue_yoy", "gross_margin"):
            val = fund.get(key)
            if val is not None:
                snap[key] = val
    except Exception:
        pass
    return snap


def screen(conditions: list[dict], universe_key: str = "hs300", limit: int = 50) -> dict:
    validate_conditions(conditions)
    members = load_universe(universe_key)
    try:
        spot = load_spot()
        spot_map = {str(r.symbol).zfill(6): r for r in spot.itertuples()}
    except Exception:
        spot_map = {}

    hits = []
    scanned = 0
    skipped = 0
    for m in members:
        scanned += 1
        row = _tech_row(m["symbol"])
        if row is None:
            skipped += 1
            continue
        spot_row = spot_map.get(m["symbol"])
        if spot_row is not None:
            for field in ("pe", "pb", "turnover", "mv", "pct_chg", "volume_ratio", "price"):
                val = getattr(spot_row, field, None)
                if val is not None and field not in row:
                    try:
                        row[field] = float(val)
                    except (TypeError, ValueError):
                        row[field] = val
            if getattr(spot_row, "pct_chg", None) is not None:
                row["pct_chg"] = float(spot_row.pct_chg)
            if getattr(spot_row, "name", None):
                row["name"] = str(spot_row.name)
        row.setdefault("name", m.get("name") or stock_name(m["symbol"]))

        ok = True
        for cond in conditions:
            field = cond.get("field")
            op = cond.get("op", ">")
            raw = cond.get("value")
            if field not in row or row[field] is None:
                ok = False
                break
            left = row[field]
            if field in ENUM_FIELDS:
                if str(left) != str(raw):
                    ok = False
                    break
                continue
            try:
                right = float(raw)
                left_f = float(left)
            except (TypeError, ValueError):
                ok = False
                break
            fn = OPS.get(op)
            if fn is None or not fn(left_f, right):
                ok = False
                break
        if ok:
            hits.append(hit_from_row(m["symbol"], row))
        if len(hits) >= limit:
            break

    return {
        "universe": universe_key,
        "scanned": scanned,
        "skipped": skipped,
        "count": len(hits),
        "hits": hits,
    }


def hit_from_row(symbol: str, row: dict) -> dict:
    return {
        "symbol": symbol,
        "name": row.get("name") or stock_name(symbol),
        "close": round(row.get("close") or 0, 3) if row.get("close") is not None else None,
        "pct_chg": _round(row.get("pct_chg")),
        "rsi14": _round(row.get("rsi14")),
        "vol_ratio": _round(row.get("vol_ratio")),
        "turnover": _round(row.get("turnover")),
        "macd_cross": row.get("macd_cross"),
        "ma_align": row.get("ma_align"),
        "pe": _round(row.get("pe")),
        "pb": _round(row.get("pb")),
        "adx14": _round(row.get("adx14")),
        "pct_20": _round(row.get("pct_20")),
        "dist_sma20": _round(row.get("dist_sma20")),
        "roe": _round(row.get("roe")),
        "net_profit_yoy": _round(row.get("net_profit_yoy")),
        "revenue_yoy": _round(row.get("revenue_yoy")),
        "gross_margin": _round(row.get("gross_margin")),
        "first_limit_up": row.get("first_limit_up"),
        "bull_pullback": row.get("bull_pullback"),
        "vol_breakout": row.get("vol_breakout"),
    }


def snapshot_hit(symbol: str) -> dict:
    """Build a screen-table row for one stock so it can be added to a static list."""
    from qt.data import load_cached_bars, normalize_symbol

    code = normalize_symbol(symbol)
    row = _tech_row(code) or {}
    row.setdefault("name", stock_name(code))
    row.setdefault("symbol", code)
    if row.get("close") is None:
        df = load_cached_bars(code)
        if df is not None and not df.empty:
            row["close"] = float(df["close"].iloc[-1])
            if "pct_chg" not in row and len(df) >= 2:
                prev = float(df["close"].iloc[-2])
                last = float(df["close"].iloc[-1])
                if prev:
                    row["pct_chg"] = (last / prev - 1) * 100
    return hit_from_row(code, row)


def _round(v, n=2):
    if v is None:
        return None
    try:
        return round(float(v), n)
    except (TypeError, ValueError):
        return None
