"""Cached-stock snapshot for the homepage wall: classify, search, filter."""

from __future__ import annotations

import json
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from qt.alerts import load_alerts
from qt.config import CACHE_DIR
from qt.data import list_cached_symbols, load_cached_bars, load_universe, stock_name
from qt.indicators import enrich, last_snapshot
from qt.sectors import (
    ensure_sectors,
    fetch_limit_up_codes,
    is_limit_up_by_pct,
    load_sectors,
    lookup_sectors,
)
from qt.signals import _regime
from qt.watchlist import watch_symbols

DASH_PATH = CACHE_DIR / "dashboard.json"
_build_lock = threading.Lock()
_building = False

BOARDS = ("沪市主板", "深市主板", "中小板", "其他")
BANDS = ("5元以下", "5–10元", "10–15元", "15–20元", "20元以上")
STANCES = ("偏多", "观望", "偏空")
RSI_ZONES = ("超卖", "中性", "超买")


def board_of(symbol: str) -> str:
    s = str(symbol).zfill(6)
    if s.startswith(("600", "601", "603", "605")):
        return "沪市主板"
    if s.startswith(("000", "001")):
        return "深市主板"
    if s.startswith(("002", "003")):
        return "中小板"
    return "其他"


def price_band(close: float | None) -> str:
    if close is None:
        return "其他"
    if close <= 5:
        return "5元以下"
    if close <= 10:
        return "5–10元"
    if close <= 15:
        return "10–15元"
    if close <= 20:
        return "15–20元"
    return "20元以上"


def rsi_zone(rsi: float | None) -> str:
    if rsi is None:
        return "中性"
    if rsi < 30:
        return "超卖"
    if rsi > 70:
        return "超买"
    return "中性"


def _stance(snap: dict) -> tuple[str, str, float]:
    rsi = snap.get("rsi14")
    sma5, sma20, sma60 = snap.get("sma5"), snap.get("sma20"), snap.get("sma60")
    hist = snap.get("macd_hist")
    score = 0.0
    if sma5 and sma20 and sma60:
        if sma5 > sma20 > sma60:
            score += 1.0
        elif sma5 < sma20 < sma60:
            score -= 1.0
    if rsi is not None:
        if rsi < 35:
            score += 0.6
        elif rsi > 65:
            score -= 0.6
    if hist is not None:
        score += 0.4 if hist > 0 else -0.4
    if score > 0.6:
        return "偏多", "buy", round(score, 3)
    if score < -0.6:
        return "偏空", "sell", round(score, 3)
    return "观望", "hold", round(score, 3)


def _round(v, n=2):
    if v is None:
        return None
    try:
        return round(float(v), n)
    except (TypeError, ValueError):
        return None


def classify_symbol(
    symbol: str,
    name: str | None = None,
    *,
    sectors: dict | None = None,
    zt_codes: set[str] | None = None,
) -> dict | None:
    df = load_cached_bars(symbol)
    if df is None or len(df) < 25:
        return None
    if len(df) > 90:
        df = df.iloc[-90:]
    try:
        x = enrich(df)
        snap = last_snapshot(x)
    except Exception:
        return None
    close = snap.get("close")
    prev = snap.get("prev_close")
    pct = None
    if close and prev:
        pct = (close / prev - 1) * 100
    stance, stance_id, score = _stance(snap)
    try:
        regime, _ = _regime(snap)
    except Exception:
        regime = "震荡整理"
    spark = [_round(v, 3) for v in x["close"].iloc[-20:].tolist()]
    nm = name or stock_name(symbol)
    industry, concepts = lookup_sectors(symbol, sectors)
    limit_up = False
    if zt_codes is not None and symbol in zt_codes:
        limit_up = True
    elif is_limit_up_by_pct(symbol, pct, nm):
        limit_up = True
    return {
        "symbol": symbol,
        "name": nm,
        "board": board_of(symbol),
        "band": price_band(close),
        "industry": industry or "未分类",
        "concepts": concepts,
        "limit_up": limit_up,
        "rsi_zone": rsi_zone(snap.get("rsi14")),
        "stance": stance,
        "stance_id": stance_id,
        "regime": regime,
        "score": score,
        "close": _round(close, 3),
        "pct_chg": _round(pct, 2),
        "pct_5": _round(snap.get("pct_5"), 2),
        "pct_20": _round(snap.get("pct_20"), 2),
        "rsi14": _round(snap.get("rsi14"), 1),
        "vol_ratio": _round(snap.get("vol_ratio"), 2),
        "macd_hist": _round(snap.get("macd_hist"), 3),
        "as_of": snap.get("date"),
        "spark": spark,
        "alert": None,
    }


def _summarize(rows: list[dict]) -> dict:
    boards, bands, stances, zones, regimes = Counter(), Counter(), Counter(), Counter(), Counter()
    industries, concepts = Counter(), Counter()
    up = down = 0
    pcts = []
    limit_rows = []
    for r in rows:
        boards[r.get("board") or "其他"] += 1
        bands[r.get("band") or "其他"] += 1
        stances[r.get("stance") or "观望"] += 1
        zones[r.get("rsi_zone") or "中性"] += 1
        regimes[r.get("regime") or "震荡整理"] += 1
        ind = r.get("industry") or "未分类"
        industries[ind] += 1
        for c in r.get("concepts") or []:
            concepts[c] += 1
        pct = r.get("pct_chg")
        if pct is not None:
            pcts.append(pct)
            if pct > 0:
                up += 1
            elif pct < 0:
                down += 1
        if r.get("limit_up"):
            limit_rows.append(r)

    by_industry: dict[str, list] = {}
    by_concept: dict[str, list] = {}
    for r in limit_rows:
        ind = r.get("industry") or "未分类"
        by_industry.setdefault(ind, []).append(
            {"symbol": r["symbol"], "name": r.get("name"), "pct_chg": r.get("pct_chg")}
        )
        for c in r.get("concepts") or ["未标注概念"]:
            by_concept.setdefault(c, []).append(
                {"symbol": r["symbol"], "name": r.get("name"), "pct_chg": r.get("pct_chg")}
            )

    concept_lu = sorted(by_concept.items(), key=lambda kv: len(kv[1]), reverse=True)[:20]
    industry_lu = sorted(by_industry.items(), key=lambda kv: len(kv[1]), reverse=True)
    top_industries = industries.most_common(40)
    top_concepts = concepts.most_common(40)

    return {
        "boards": {k: boards.get(k, 0) for k in BOARDS},
        "bands": {k: bands.get(k, 0) for k in BANDS},
        "stances": {k: stances.get(k, 0) for k in STANCES},
        "rsi_zones": {k: zones.get(k, 0) for k in RSI_ZONES},
        "regimes": dict(regimes),
        "industries": {k: v for k, v in top_industries},
        "concepts": {k: v for k, v in top_concepts},
        "up": up,
        "down": down,
        "flat": max(0, len(rows) - up - down),
        "avg_pct": round(sum(pcts) / len(pcts), 2) if pcts else 0,
        "limit_up": len(limit_rows),
        "limit_up_by_industry": {k: v for k, v in industry_lu},
        "limit_up_by_concept": {k: v for k, v in concept_lu},
        "alerts": {
            "buy": sum(1 for r in rows if r.get("alert") == "buy"),
            "sell": sum(1 for r in rows if r.get("alert") == "sell"),
        },
    }


def _attach_alerts(rows: list[dict]) -> None:
    alerts = load_alerts()
    kinds = {}
    for a in alerts.get("buys") or []:
        kinds[a["symbol"]] = {**a, "kind": "buy"}
    for a in alerts.get("sells") or []:
        kinds[a["symbol"]] = {**a, "kind": "sell"}
    for r in rows:
        hit = kinds.get(r["symbol"])
        if not hit:
            continue
        r["alert"] = hit["kind"]
        r["stance"] = hit.get("stance") or r["stance"]
        r["stance_id"] = hit["kind"]
        r["score"] = hit.get("score", r["score"])
        r["regime"] = hit.get("regime") or r["regime"]
        r["reasons"] = hit.get("reasons") or []


def build_dashboard(universe_key: str = "low20", progress: dict | None = None) -> dict:
    try:
        members = load_universe(universe_key, refresh=False)
        names = {m["symbol"]: m.get("name") for m in members}
        pool = [m["symbol"] for m in members]
    except Exception:
        names, pool = {}, []
    cached = set(list_cached_symbols())
    symbols = [s for s in pool if s in cached] or sorted(cached)
    total = len(symbols)
    if progress is not None:
        progress.update({"phase": "dashboard", "scan_done": 0, "scan_total": total})

    try:
        sectors = load_sectors()
        if not sectors.get("built_at"):
            from qt.sectors import ensure_sectors_async

            ensure_sectors_async(force=False)
    except Exception:
        sectors = load_sectors()

    as_of = None
    zt_codes: set[str] = set()
    try:
        zt_codes = fetch_limit_up_codes()
    except Exception:
        zt_codes = set()

    rows: list[dict] = []

    def _one(code: str):
        return classify_symbol(code, names.get(code), sectors=sectors, zt_codes=zt_codes or None)

    done = 0
    with ThreadPoolExecutor(max_workers=8) as pool_ex:
        futs = {pool_ex.submit(_one, code): code for code in symbols}
        for fut in as_completed(futs):
            done += 1
            if progress is not None and (done % 8 == 0 or done == total):
                progress["scan_done"] = done
                progress["done"] = done
                progress["total"] = total
            try:
                row = fut.result()
            except Exception:
                row = None
            if row:
                rows.append(row)
                if as_of is None and row.get("as_of"):
                    as_of = row["as_of"]

    if not zt_codes and as_of:
        try:
            zt_codes = fetch_limit_up_codes(as_of)
            if zt_codes:
                for r in rows:
                    if r["symbol"] in zt_codes:
                        r["limit_up"] = True
        except Exception:
            pass

    rows.sort(key=lambda r: r["symbol"])
    _attach_alerts(rows)
    payload = {
        "built_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "universe": universe_key,
        "count": len(rows),
        "as_of": as_of,
        "summary": _summarize(rows),
        "stocks": rows,
        "sectors_at": sectors.get("built_at"),
    }
    DASH_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    if progress is not None:
        progress["scan_done"] = total
        progress["dash_count"] = len(rows)
    return payload


def load_dashboard() -> dict:
    if not DASH_PATH.exists():
        ensure_dashboard()
        return {"built_at": None, "count": 0, "summary": _summarize([]), "stocks": [], "building": True}
    try:
        data = json.loads(DASH_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"built_at": None, "count": 0, "summary": _summarize([]), "stocks": []}
    watched = watch_symbols()
    sectors = load_sectors()
    enriched = False
    for row in data.get("stocks") or []:
        row["watched"] = row.get("symbol") in watched
        row.setdefault("industry", "未分类")
        row.setdefault("concepts", [])
        row.setdefault("limit_up", False)
        if sectors.get("built_at") and (row.get("industry") in (None, "", "未分类") or not row.get("concepts")):
            ind, cons = lookup_sectors(row["symbol"], sectors)
            if row.get("industry") in (None, "", "未分类") and ind:
                row["industry"] = ind
                enriched = True
            if not row.get("concepts") and cons:
                row["concepts"] = cons
                enriched = True
    if enriched:
        data["summary"] = _summarize(data.get("stocks") or [])
        data["sectors_at"] = sectors.get("built_at")
    data["watch_count"] = len(watched)
    return data


def ensure_dashboard() -> None:
    global _building
    if DASH_PATH.exists():
        return
    with _build_lock:
        if _building:
            return
        _building = True

    def _run():
        global _building
        try:
            build_dashboard("low20")
        except Exception:
            pass
        finally:
            _building = False

    threading.Thread(target=_run, daemon=True).start()


def search_stocks(q: str, limit: int = 12) -> list[dict]:
    q = (q or "").strip().lower()
    if not q:
        return []
    data = load_dashboard()
    rows = data.get("stocks") or []
    if not rows:
        from qt.data import load_name_map

        hits = []
        for code, name in load_name_map().items():
            if q in code.lower() or q in str(name).lower():
                hits.append({"symbol": code, "name": name, "close": None, "pct_chg": None, "stance": None})
            if len(hits) >= limit:
                break
        return hits

    scored = []
    for r in rows:
        code = r["symbol"]
        name = str(r.get("name") or "")
        hay = f"{code} {name}".lower()
        if hay.startswith(q) or code.startswith(q):
            rank = 0
        elif q in code:
            rank = 1
        elif name.lower().startswith(q) or q in name.lower():
            rank = 2
        else:
            continue
        scored.append((rank, code, r))
    scored.sort(key=lambda x: (x[0], x[1]))
    out = []
    for _, _, r in scored[:limit]:
        out.append(
            {
                "symbol": r["symbol"],
                "name": r.get("name"),
                "close": r.get("close"),
                "pct_chg": r.get("pct_chg"),
                "stance": r.get("stance"),
                "industry": r.get("industry"),
            }
        )
    return out
