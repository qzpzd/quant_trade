"""FastAPI entry: uvicorn server:app --host 127.0.0.1 --port 8765"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from qt.alerts import load_alerts, scan_alerts, watchlist_alerts
from qt.auction import analyze_auction
from qt.backtest_engine import list_strategies, run_backtest
from qt.calendar_data import calendar_day, calendar_month
from qt.dashboard import build_dashboard, load_dashboard, search_stocks
from qt.sectors import ensure_sectors_async, sectors_status
from qt.data import (
    bars_to_records,
    load_bars,
    load_universe,
    normalize_symbol,
    stock_name,
)
from qt.paths import resource_dir
from qt.indicators import enrich
from qt.jobs import start_scheduler, start_update, status as cache_status
from qt.predict import forecast
from qt.library import (
    add_screen_hit,
    delete_pattern,
    delete_screen,
    get_pattern,
    get_screen,
    load_patterns,
    load_screens,
    remove_screen_hit,
    save_pattern,
    save_screen,
)
from qt.screener import SCREEN_FIELDS, screen, snapshot_hit, validate_conditions
from qt.signals import current_view, detect_signals
from qt.similarity import bars_for_match, find_similar, find_similar_many, query_frame, zscore
from qt.study import study_hits
from qt.live import (
    get_live_minutes,
    get_live_quote,
    get_quotes,
    get_watchlist_quotes,
    live_status,
)
from qt.watchlist import add_watch, load_watchlist, remove_watch


@asynccontextmanager
async def lifespan(_: FastAPI):
    start_scheduler()
    try:
        ensure_sectors_async(force=False)
    except Exception:
        pass
    yield


app = FastAPI(title="形迹 QuantTrade", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def no_store_ui(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".html", ".js", ".css")):
        response.headers["Cache-Control"] = "no-store"
    return response


class BacktestIn(BaseModel):
    symbol: str | None = None
    strategy: str | None = "trend"
    strategies: list[str] = Field(default_factory=list)
    start: str = "2020-01-01"
    end: str = "2024-12-31"
    cash: float = 100000
    pattern_ids: list[str] = Field(default_factory=list)
    screen_id: str | None = None
    max_symbols: int = 8


class PredictIn(BaseModel):
    symbol: str
    lookback: int = 30
    horizon: int = 10


class Condition(BaseModel):
    field: str
    op: str = ">"
    value: Any


class SimilarIn(BaseModel):
    symbol: str | None = None
    start: str | None = None
    end: str | None = None
    universe: str = "hs300"
    top_n: int = 12
    lookback_days: int = 0
    pattern_ids: list[str] = Field(default_factory=list)
    include_current: bool = True
    analyze: bool = True


class PatternIn(BaseModel):
    name: str
    symbol: str
    start: str
    end: str


class ScreenSaveIn(BaseModel):
    name: str
    mode: str = "dynamic"
    universe: str = "low20"
    conditions: list[Condition] = Field(default_factory=list)
    hits: list[dict] | None = None
    limit: int = 50


class ScreenIn(BaseModel):
    universe: str = "hs300"
    conditions: list[Condition] = Field(default_factory=list)
    limit: int = 40


class SyncIn(BaseModel):
    universe: str = "hs300"


class WatchIn(BaseModel):
    symbol: str


class ScreenHitIn(BaseModel):
    symbol: str


def _err(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@app.get("/api/health")
def health():
    return {"ok": True, "name": "形迹"}


@app.get("/api/strategies")
def strategies():
    return {"strategies": list_strategies()}


@app.get("/api/quote/{symbol}")
def quote(symbol: str, start: str = "2020-01-01", end: str | None = None):
    symbol = normalize_symbol(symbol)
    try:
        df = load_bars(symbol, start, end)
    except Exception as exc:
        raise _err(exc)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"未找到 {symbol} 的行情")
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last
    close = float(last["close"])
    prev_close = float(prev["close"])
    chg = (close / prev_close - 1) * 100 if prev_close else 0

    def _field(key: str) -> float | None:
        if key not in df.columns:
            return None
        val = last[key]
        try:
            if val != val:  # NaN
                return None
            return float(val)
        except (TypeError, ValueError):
            return None

    return {
        "symbol": symbol,
        "name": stock_name(symbol),
        "date": df.index[-1].strftime("%Y-%m-%d"),
        "close": close,
        "open": float(last["open"]),
        "high": float(last["high"]),
        "low": float(last["low"]),
        "volume": float(last["volume"]),
        "amount": _field("amount"),
        "turnover": _field("turnover"),
        "pct_chg": round(chg, 2),
        "bars": bars_to_records(df),
    }


@app.get("/api/analyze/{symbol}")
def analyze(symbol: str, start: str = "2022-01-01", end: str | None = None):
    symbol = normalize_symbol(symbol)
    try:
        df = load_bars(symbol, start, end)
        view = current_view(df)
        x = enrich(df)
    except Exception as exc:
        raise _err(exc)
    keep = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "turnover",
        "pct_chg",
        "vol_ratio",
        "ema20",
        "ema60",
        "sma20",
        "rsi14",
        "macd_dif",
        "macd_dea",
        "macd_hist",
        "bb_upper",
        "bb_mid",
        "bb_lower",
    ]
    cols = [c for c in keep if c in x.columns]
    return {
        "symbol": symbol,
        "name": stock_name(symbol),
        **view,
        "bars": bars_to_records(x[cols]),
        "signal_count": len(detect_signals(df)),
    }


@app.post("/api/backtest")
def backtest(body: BacktestIn):
    try:
        strategies = [s for s in (body.strategies or []) if s]
        if not strategies and body.strategy:
            strategies = [body.strategy]
        if not strategies:
            raise RuntimeError("请至少选择一个策略")

        jobs: list[dict] = []
        if body.pattern_ids:
            for pid in body.pattern_ids:
                item = get_pattern(pid)
                if item is None:
                    raise RuntimeError(f"未找到形态 {pid}")
                jobs.append(
                    {
                        "symbol": normalize_symbol(item["symbol"]),
                        "start": body.start or item.get("start") or "2020-01-01",
                        "end": body.end or item.get("end") or body.end,
                        "label": item.get("name") or item["symbol"],
                        "source": "pattern",
                        "source_id": pid,
                    }
                )
        elif body.screen_id:
            scr = get_screen(body.screen_id)
            if scr is None:
                raise RuntimeError(f"未找到条件 {body.screen_id}")
            hits = list(scr.get("hits") or [])
            if not hits and (scr.get("conditions") or []):
                from qt.screener import screen as run_screen

                out = run_screen(
                    [{"field": c.get("field"), "op": c.get("op", ">"), "value": c.get("value")} for c in scr["conditions"]],
                    scr.get("universe") or "demo",
                    limit=max(1, min(body.max_symbols, 20)),
                )
                hits = out.get("hits") or []
            if not hits:
                raise RuntimeError("该条件名单为空，请先选股或加入静态名单")
            for h in hits[: max(1, min(body.max_symbols, 20))]:
                code = normalize_symbol(h.get("symbol") or "")
                if not code:
                    continue
                jobs.append(
                    {
                        "symbol": code,
                        "start": body.start,
                        "end": body.end,
                        "label": h.get("name") or code,
                        "source": "screen",
                        "source_id": body.screen_id,
                    }
                )
        else:
            if not body.symbol:
                raise RuntimeError("请填写股票代码，或选择已保存形态/条件")
            jobs.append(
                {
                    "symbol": normalize_symbol(body.symbol),
                    "start": body.start,
                    "end": body.end,
                    "label": stock_name(normalize_symbol(body.symbol)),
                    "source": "symbol",
                    "source_id": None,
                }
            )

        if not jobs:
            raise RuntimeError("没有可回测的标的")

        results = []
        warnings = []
        for job in jobs:
            for sk in strategies:
                try:
                    r = run_backtest(job["symbol"], sk, job["start"], job["end"], cash=body.cash)
                    r["job_label"] = job["label"]
                    r["source"] = job["source"]
                    r["source_id"] = job.get("source_id")
                    # 多结果时去掉沉重 bars，前端只保留首个标的的 K 线
                    if len(jobs) > 1 or len(strategies) > 1:
                        r = {**r, "bars": r.get("bars") if len(results) == 0 else []}
                    results.append(r)
                    if r.get("warning"):
                        warnings.append(f"{r['symbol']}/{r['strategy_name']}: {r['warning']}")
                except Exception as exc:
                    results.append(
                        {
                            "symbol": job["symbol"],
                            "name": job["label"],
                            "strategy": sk,
                            "strategy_name": sk,
                            "job_label": job["label"],
                            "error": str(exc),
                            "return_pct": None,
                            "equity": [],
                            "trades": [],
                            "bars": [],
                        }
                    )

        compare = []
        for r in results:
            if r.get("error"):
                compare.append(
                    {
                        "symbol": r.get("symbol"),
                        "name": r.get("name") or r.get("job_label"),
                        "strategy": r.get("strategy"),
                        "strategy_name": r.get("strategy_name"),
                        "error": r["error"],
                    }
                )
                continue
            compare.append(
                {
                    "symbol": r["symbol"],
                    "name": r.get("name") or r.get("job_label"),
                    "strategy": r["strategy"],
                    "strategy_name": r["strategy_name"],
                    "return_pct": r["return_pct"],
                    "buy_hold_pct": r.get("buy_hold_pct"),
                    "max_drawdown_pct": r.get("max_drawdown_pct"),
                    "sharpe": r.get("sharpe"),
                    "win_rate_pct": r.get("win_rate_pct"),
                    "round_trips": r.get("round_trips"),
                    "final_value": r.get("final_value"),
                }
            )

        primary = next((r for r in results if not r.get("error")), None)
        return {
            "count": len(results),
            "strategies": strategies,
            "jobs": len(jobs),
            "results": results,
            "compare": compare,
            "primary": primary,
            "warning": "；".join(warnings) if warnings else None,
        }
    except Exception as exc:
        raise _err(exc)


@app.post("/api/predict")
def predict(body: PredictIn):
    try:
        return forecast(normalize_symbol(body.symbol), lookback=body.lookback, horizon=body.horizon)
    except Exception as exc:
        raise _err(exc)


@app.post("/api/similar")
def similar(body: SimilarIn):
    try:
        queries = []
        for pid in body.pattern_ids or []:
            item = get_pattern(pid)
            if item is None:
                raise RuntimeError(f"未找到形态 {pid}")
            queries.append(item)
        if body.include_current and body.symbol and body.start and body.end:
            queries.append(
                {
                    "id": "current",
                    "name": f"{body.symbol} {body.start}~{body.end}",
                    "symbol": normalize_symbol(body.symbol),
                    "start": body.start,
                    "end": body.end,
                }
            )
        if not queries and body.symbol and body.start and body.end:
            queries.append(
                {
                    "id": "current",
                    "name": body.symbol,
                    "symbol": normalize_symbol(body.symbol),
                    "start": body.start,
                    "end": body.end,
                }
            )
        if len(queries) == 1 and not body.pattern_ids:
            q = queries[0]
            out = find_similar(
                q["symbol"],
                q["start"],
                q["end"],
                universe_key=body.universe,
                top_n=body.top_n,
                lookback_days=body.lookback_days,
            )
        else:
            out = find_similar_many(
                queries,
                universe_key=body.universe,
                top_n=body.top_n,
                lookback_days=body.lookback_days,
            )
        if body.analyze:
            out["study"] = study_hits(out.get("matches") or [])
        return out
    except Exception as exc:
        raise _err(exc)


@app.get("/api/patterns")
def patterns_list():
    return {"items": load_patterns()}


@app.post("/api/patterns")
def patterns_add(body: PatternIn):
    try:
        symbol = normalize_symbol(body.symbol)
        src = bars_for_match(symbol)
        qf = query_frame(src, body.start, body.end)
        name = (body.name or "").strip()
        if not name:
            raise RuntimeError("请填写形态名称")

        def _series_list(col: str) -> list[float | None]:
            if col not in qf.columns:
                return []
            out = []
            for x in qf[col].values:
                try:
                    if x != x:
                        out.append(None)
                    else:
                        out.append(float(x))
                except (TypeError, ValueError):
                    out.append(None)
            return out

        item = save_pattern(
            {
                "name": name,
                "symbol": symbol,
                "stock_name": stock_name(symbol),
                "start": qf.index[0].strftime("%Y-%m-%d"),
                "end": qf.index[-1].strftime("%Y-%m-%d"),
                "window": int(len(qf)),
                "query_dates": [d.strftime("%Y-%m-%d") for d in qf.index],
                "query_close": [float(x) for x in qf["close"].values],
                "query_volume": _series_list("volume"),
                "query_turnover": _series_list("turnover"),
                "query_norm": zscore(qf["close"].values).tolist(),
            }
        )
        return {"ok": True, "item": item, "items": load_patterns()}
    except Exception as exc:
        raise _err(exc)


@app.delete("/api/patterns/{pid}")
def patterns_del(pid: str):
    try:
        return delete_pattern(pid)
    except Exception as exc:
        raise _err(exc)


@app.get("/api/screens")
def screens_list():
    items = []
    for s in load_screens():
        items.append(
            {
                "id": s.get("id"),
                "name": s.get("name"),
                "mode": s.get("mode"),
                "universe": s.get("universe"),
                "count": s.get("count") if s.get("mode") == "static" else None,
                "conditions": s.get("conditions") or [],
                "created_at": s.get("created_at"),
                "updated_at": s.get("updated_at"),
            }
        )
    return {"items": items}


@app.post("/api/screens")
def screens_add(body: ScreenSaveIn):
    try:
        name = (body.name or "").strip()
        if not name:
            raise RuntimeError("请填写条件名称")
        mode = "static" if body.mode == "static" else "dynamic"
        conds = [c.model_dump() if hasattr(c, "model_dump") else c.dict() for c in body.conditions]
        validate_conditions(conds)
        hits = list(body.hits or [])
        if mode != "static":
            hits = []
        item = save_screen(
            {
                "name": name,
                "mode": mode,
                "universe": body.universe,
                "conditions": conds,
                "hits": hits if mode == "static" else [],
                "count": len(hits) if mode == "static" else None,
            }
        )
        return {"ok": True, "item": item, "items": load_screens()}
    except Exception as exc:
        raise _err(exc)


@app.get("/api/screens/{sid}")
def screens_get(sid: str):
    item = get_screen(sid)
    if item is None:
        raise HTTPException(status_code=404, detail="未找到该条件")
    try:
        if item.get("mode") == "dynamic":
            ran = screen(item.get("conditions") or [], universe_key=item.get("universe") or "low20", limit=50)
            return {**item, **ran, "frozen": False}
        return {
            **item,
            "hits": item.get("hits") or [],
            "count": len(item.get("hits") or []),
            "scanned": None,
            "skipped": None,
            "frozen": True,
        }
    except Exception as exc:
        raise _err(exc)


@app.delete("/api/screens/{sid}")
def screens_del(sid: str):
    try:
        return delete_screen(sid)
    except Exception as exc:
        raise _err(exc)


@app.post("/api/screens/{sid}/hits")
def screens_add_hit(sid: str, body: ScreenHitIn):
    try:
        hit = snapshot_hit(normalize_symbol(body.symbol))
        item = add_screen_hit(sid, hit)
        return {"ok": True, "item": item}
    except Exception as exc:
        raise _err(exc)


@app.delete("/api/screens/{sid}/hits/{symbol}")
def screens_del_hit(sid: str, symbol: str):
    try:
        item = remove_screen_hit(sid, normalize_symbol(symbol))
        return {"ok": True, "item": item}
    except Exception as exc:
        raise _err(exc)


@app.get("/api/screen/fields")
def screen_fields():
    return {"fields": SCREEN_FIELDS}


@app.post("/api/screen")
def screen_api(body: ScreenIn):
    try:
        conds = [c.model_dump() if hasattr(c, "model_dump") else c.dict() for c in body.conditions]
        return screen(conds, universe_key=body.universe, limit=body.limit)
    except Exception as exc:
        raise _err(exc)


@app.get("/api/universe/{key}")
def universe(key: str):
    try:
        members = load_universe(key)
    except Exception as exc:
        raise _err(exc)
    return {"key": key, "count": len(members), "members": members[:20], "total": len(members)}


@app.get("/api/cache/status")
def cache_status_api():
    return cache_status()


@app.post("/api/cache/update")
def cache_update(body: SyncIn | None = None):
    key = body.universe if body else "low20"
    return start_update(key, "manual")


@app.get("/api/alerts")
def alerts_api():
    return load_alerts()


@app.post("/api/alerts/refresh")
def alerts_refresh():
    try:
        payload = scan_alerts("low20")
        try:
            build_dashboard("low20")
        except Exception:
            pass
        return payload
    except Exception as exc:
        raise _err(exc)


@app.get("/api/alerts/watchlist")
def alerts_watchlist_api():
    return watchlist_alerts()


@app.get("/api/dashboard")
def dashboard_api():
    return load_dashboard()


@app.post("/api/dashboard/refresh")
def dashboard_refresh():
    try:
        return build_dashboard("low20")
    except Exception as exc:
        raise _err(exc)


@app.get("/api/sectors")
def sectors_api():
    return sectors_status()


@app.post("/api/sectors/refresh")
def sectors_refresh():
    try:
        ensure_sectors_async(force=True)
        return {"status": "started", **sectors_status()}
    except Exception as exc:
        raise _err(exc)


@app.get("/api/calendar")
def calendar_api(year: int | None = None, month: int | None = None, live: int = 0):
    try:
        now = datetime.now()
        y = year or now.year
        m = month or now.month
        return calendar_month(y, m, include_live=bool(live))
    except Exception as exc:
        raise _err(exc)


@app.get("/api/calendar/day")
def calendar_day_api(date: str, live: int = 1):
    try:
        return calendar_day(date, include_live=bool(live))
    except Exception as exc:
        raise _err(exc)


@app.get("/api/search")
def search_api(q: str = "", limit: int = 12):
    return {"q": q, "hits": search_stocks(q, limit=max(1, min(limit, 20)))}


@app.get("/api/live/status")
def live_status_api():
    return live_status()


@app.get("/api/live/spot")
def live_spot_api(symbols: str = "", force: bool = False):
    """准实时现价。symbols 逗号分隔；空则取自选。"""
    try:
        raw = [s.strip() for s in (symbols or "").split(",") if s.strip()]
        if raw:
            return get_quotes(raw, force=bool(force))
        return get_watchlist_quotes(force=bool(force))
    except Exception as exc:
        raise _err(exc)


@app.get("/api/live/quote/{symbol}")
def live_quote_api(symbol: str, force: bool = False):
    try:
        return get_live_quote(symbol, force=bool(force))
    except Exception as exc:
        raise _err(exc)


@app.get("/api/live/minutes/{symbol}")
def live_minutes_api(symbol: str, ndays: int = 1, force: bool = False):
    try:
        return get_live_minutes(symbol, ndays=max(1, min(int(ndays), 5)), force=bool(force))
    except Exception as exc:
        raise _err(exc)


@app.get("/api/watchlist")
def watchlist_api():
    items = load_watchlist()
    return {"count": len(items), "items": items}


@app.post("/api/watchlist")
def watchlist_add(body: WatchIn):
    try:
        return add_watch(body.symbol)
    except Exception as exc:
        raise _err(exc)


@app.delete("/api/watchlist/{symbol}")
def watchlist_del(symbol: str):
    try:
        return remove_watch(symbol)
    except Exception as exc:
        raise _err(exc)


@app.get("/api/auction/{symbol}")
def auction(symbol: str):
    try:
        return analyze_auction(normalize_symbol(symbol))
    except Exception as exc:
        raise _err(exc)


@app.post("/api/universe/sync")
def universe_sync(body: SyncIn):
    return start_update(body.universe, "manual")


@app.get("/api/universe/sync/status")
def universe_sync_status():
    return cache_status()


web_dir = resource_dir("web")
if not web_dir.is_dir():
    raise RuntimeError(f"未找到 web 静态目录: {web_dir}")
app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")
