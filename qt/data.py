"""OHLCV fetch with local pickle cache. East Money via akshare."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from qt.config import (
    BARS_DIR,
    CACHE_DIR,
    DEFAULT_START,
    FALLBACK_UNIVERSE,
    INDEX_UNIVERSES,
    LOW_PRICE_MAX,
    MAIN_BOARD_PREFIXES,
)

HIST_COLMAP = {
    "日期": "date",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "成交额": "amount",
    "涨跌幅": "pct_chg",
    "换手率": "turnover",
    "股票代码": "code",
}

SPOT_COLMAP = {
    "代码": "symbol",
    "名称": "name",
    "最新价": "price",
    "涨跌幅": "pct_chg",
    "涨跌额": "chg",
    "成交量": "volume",
    "成交额": "amount",
    "最高": "high",
    "最低": "low",
    "今开": "open",
    "昨收": "pre_close",
    "量比": "volume_ratio",
    "换手率": "turnover",
    "市盈率-动态": "pe",
    "市净率": "pb",
    "总市值": "mv",
    "流通市值": "float_mv",
    "60日涨跌幅": "pct_60",
    "年初至今涨跌幅": "pct_ytd",
}


def _compact(date_str: str | None) -> str:
    if not date_str:
        return ""
    return str(date_str).replace("-", "")[:8]


def _today() -> str:
    return datetime.now().strftime("%Y%m%d")


def normalize_symbol(symbol: str) -> str:
    s = str(symbol).strip().lower().replace("sh", "").replace("sz", "").replace("bj", "")
    s = s.replace(".", "")
    if s.isdigit() and len(s) < 6:
        s = s.zfill(6)
    return s


def _cache_path(symbol: str, adjust: str) -> Path:
    return BARS_DIR / f"{normalize_symbol(symbol)}_{adjust}.pkl"


def list_cached_symbols(adjust: str = "qfq") -> list[str]:
    out = []
    for path in BARS_DIR.glob(f"*_{adjust}.pkl"):
        code = path.name.replace(f"_{adjust}.pkl", "")
        if code.isdigit():
            out.append(code)
    return sorted(set(out))


def load_cached_bars(symbol: str, adjust: str = "qfq") -> pd.DataFrame | None:
    path = _cache_path(symbol, adjust)
    if not path.exists():
        return None
    df = pd.read_pickle(path)
    df.index = pd.to_datetime(df.index)
    return _ensure_turnover_percent(df.sort_index())


def _turnover_as_percent(series: pd.Series) -> pd.Series:
    """统一换手率为百分比（如 0.54 表示 0.54%）。新浪日线多为小数比例，东财多为百分数。"""
    s = pd.to_numeric(series, errors="coerce")
    finite = s.replace([np.inf, -np.inf], np.nan).dropna()
    if finite.empty:
        return s
    # 已有 >1 的百分数，视为东财口径，不再放大
    if bool((finite > 1).any()):
        return s
    med = float(finite.median())
    mx = float(finite.max())
    # 小数比例特征：最大值通常 <1 且中位数远小于 0.1（如 0.005≈0.5%）
    if mx < 1.0 and med < 0.1:
        return s * 100.0
    return s


def _ensure_turnover_percent(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "turnover" not in df.columns:
        return df
    out = df.copy()
    out["turnover"] = _turnover_as_percent(out["turnover"])
    return out


def _normalize_hist(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=HIST_COLMAP)
    if "date" not in df.columns:
        raise RuntimeError("行情缺少日期列")
    keep = [c for c in ["date", "open", "high", "low", "close", "volume", "amount", "pct_chg", "turnover"] if c in df.columns]
    df = df[keep].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])
    return _ensure_turnover_percent(df)

def _sina_symbol(symbol: str) -> str:
    if symbol.startswith("6"):
        return f"sh{symbol}"
    if symbol.startswith("0") or symbol.startswith("3"):
        return f"sz{symbol}"
    if symbol.startswith("8") or symbol.startswith("4"):
        return f"bj{symbol}"
    return symbol


def _download_hist(symbol: str, start: str, end: str, adjust: str) -> pd.DataFrame:
    import akshare as ak

    symbol = normalize_symbol(symbol)
    last_err = None
    for attempt in range(3):
        try:
            df = ak.stock_zh_a_daily(
                symbol=_sina_symbol(symbol),
                start_date=start,
                end_date=end,
                adjust=adjust,
            )
            if df is not None and not df.empty:
                return _normalize_hist(df)
        except Exception as exc:
            last_err = exc
        try:
            df = ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start,
                end_date=end,
                adjust=adjust,
            )
            if df is not None and not df.empty:
                return _normalize_hist(df)
        except Exception as exc:
            last_err = exc
        time.sleep(0.7 * (attempt + 1))
    raise RuntimeError(f"获取 {symbol} 行情失败: {last_err}")


def get_stock_data(symbol: str, start_date: str | None = None, end_date: str | None = None, adjust: str = "qfq") -> pd.DataFrame | None:
    """Return OHLCV with datetime index. Used by both the terminal and the CLI."""
    try:
        df = load_bars(symbol, start_date, end_date, adjust=adjust)
        if df is None or df.empty:
            return None
        return df[["open", "high", "low", "close", "volume"]].copy()
    except Exception as exc:
        print(f"获取数据失败: {exc}")
        return None


def load_bars(
    symbol: str,
    start_date: str | None = None,
    end_date: str | None = None,
    adjust: str = "qfq",
    refresh: bool = False,
) -> pd.DataFrame:
    symbol = normalize_symbol(symbol)
    start = _compact(start_date) or DEFAULT_START
    end = _compact(end_date) or _today()
    path = _cache_path(symbol, adjust)

    cached = None
    if path.exists() and not refresh:
        cached = pd.read_pickle(path)
        cached.index = pd.to_datetime(cached.index)
        raw_turn = cached["turnover"].copy() if "turnover" in cached.columns else None
        cached = _ensure_turnover_percent(cached)
        # 把小数比例写回缓存，避免接口一直读到 0.005 这种未换算值
        if raw_turn is not None:
            a = pd.to_numeric(raw_turn, errors="coerce").fillna(-1).to_numpy()
            b = pd.to_numeric(cached["turnover"], errors="coerce").fillna(-1).to_numpy()
            if len(a) == len(b) and not np.allclose(a, b, rtol=0, atol=1e-15):
                cached.to_pickle(path)

    start_ts, end_ts = pd.to_datetime(start), pd.to_datetime(end)
    fetch_start = start
    if cached is not None and not cached.empty:
        last = cached.index.max()
        # Re-fetch from a small overlap if cache does not cover `end`.
        if last >= end_ts and cached.index.min() <= start_ts:
            return cached.loc[start_ts:end_ts].copy()
        if last < end_ts:
            fetch_start = (last - timedelta(days=7)).strftime("%Y%m%d")
        else:
            fetch_start = start

    fresh = _download_hist(symbol, fetch_start, end, adjust)
    if cached is None or cached.empty:
        merged = fresh
    else:
        merged = pd.concat([cached, fresh])
        merged = merged[~merged.index.duplicated(keep="last")].sort_index()
    merged = _ensure_turnover_percent(merged)

    if merged is not None and not merged.empty:
        merged.to_pickle(path)

    if merged is None or merged.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    return merged.loc[start_ts:end_ts].copy()


def bars_to_records(df: pd.DataFrame) -> list[dict]:
    if df is None or df.empty:
        return []
    out = []
    for ts, row in df.iterrows():
        item = {"date": pd.Timestamp(ts).strftime("%Y-%m-%d")}
        for col in df.columns:
            val = row[col]
            item[col] = None if pd.isna(val) else float(val)
        out.append(item)
    return out


def load_spot(refresh: bool = False) -> pd.DataFrame:
    path = CACHE_DIR / "spot.pkl"
    if path.exists() and not refresh:
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        if datetime.now() - mtime < timedelta(minutes=30):
            return pd.read_pickle(path)

    import akshare as ak

    last_err = None
    df = None
    fetchers = (
        lambda: ak.stock_zh_a_spot_em(),
        lambda: ak.stock_zh_a_spot(),
    )
    for attempt in range(3):
        for fn in fetchers:
            try:
                raw = fn()
                if raw is not None and not raw.empty:
                    df = raw
                    break
            except Exception as exc:
                last_err = exc
        if df is not None:
            break
        time.sleep(0.8 * (attempt + 1))
    if df is None or df.empty:
        if path.exists():
            return pd.read_pickle(path)
        raise RuntimeError(f"获取全市场行情失败: {last_err}")

    df = df.rename(columns=SPOT_COLMAP)
    keep = [c for c in SPOT_COLMAP.values() if c in df.columns]
    df = df[keep].copy()
    df["symbol"] = df["symbol"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(6)
    for col in df.columns:
        if col in ("symbol", "name"):
            continue
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df.to_pickle(path)
    return df


_FUNDAMENTAL_COLMAP = {
    "股票代码": "symbol",
    "每股收益": "eps",
    "营业总收入-同比增长": "revenue_yoy",
    "净利润-同比增长": "net_profit_yoy",
    "净资产收益率": "roe",
    "销售毛利率": "gross_margin",
}


def _recent_report_dates(n: int = 6) -> list[str]:
    """今天及之前的季度末（YYYYMMDD），最新在前，供业绩报表回退用。"""
    today = datetime.now()
    qends = []
    for y in range(today.year - 1, today.year + 2):
        for m, d in ((3, 31), (6, 30), (9, 30), (12, 31)):
            qends.append((y, m, d))
    past = sorted(
        [qd for qd in qends if datetime(*qd) <= today],
        key=lambda qd: (qd[0], qd[1], qd[2]),
        reverse=True,
    )
    return [f"{y}{m:02d}{d:02d}" for (y, m, d) in past[:n]]


def load_fundamentals(refresh: bool = False) -> pd.DataFrame:
    """批量业绩报表（ROE/净利润同比/营收同比/毛利率），按代码索引，缓存 24h。

    数据源为东财业绩报表（stock_yjbb_em）。网络不可用时回退到缓存或空表，
    由调用方按字段缺失做降级处理。
    """
    path = CACHE_DIR / "fundamental.pkl"
    if path.exists() and not refresh:
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        if datetime.now() - mtime < timedelta(hours=24):
            return pd.read_pickle(path)

    import akshare as ak

    best = None
    best_n = 0
    for date in _recent_report_dates():
        try:
            raw = ak.stock_yjbb_em(date=date)
        except Exception:
            continue
        if raw is None or raw.empty:
            continue
        if best is None or len(raw) > best_n:
            best = raw
            best_n = len(raw)
        # 覆盖充分即可停止（A 股约 5000 只）
        if best_n >= 3000:
            break

    if best is None:
        if path.exists():
            return pd.read_pickle(path)
        return pd.DataFrame()

    df = best.rename(columns=_FUNDAMENTAL_COLMAP)
    keep = [c for c in _FUNDAMENTAL_COLMAP.values() if c in df.columns]
    df = df[keep].copy()
    df["symbol"] = df["symbol"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(6)
    df = df[df["symbol"].str.isdigit()]
    df = df.drop_duplicates(subset=["symbol"], keep="first")
    df = df.set_index("symbol").sort_index()
    for col in df.columns:
        if col == "symbol":
            continue
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df.to_pickle(path)
    return df


_FUND_MAP: dict | None = None
_FUND_MTIME: float | None = None


def fundamentals_map(refresh: bool = False) -> dict[str, dict]:
    """{代码: {roe, net_profit_yoy, revenue_yoy, gross_margin}}，进程内按 pkl 缓存。"""
    global _FUND_MAP, _FUND_MTIME
    path = CACHE_DIR / "fundamental.pkl"
    mtime = path.stat().st_mtime if path.exists() else None
    if not refresh and _FUND_MAP is not None and _FUND_MTIME == mtime:
        return _FUND_MAP

    df = load_fundamentals(refresh=refresh)
    out: dict[str, dict] = {}
    if df is not None and not df.empty:
        for sym, row in df.iterrows():
            def _v(col):
                if col not in df.columns:
                    return None
                val = row[col]
                return None if pd.isna(val) else float(val)

            out[sym] = {
                "roe": _v("roe"),
                "net_profit_yoy": _v("net_profit_yoy"),
                "revenue_yoy": _v("revenue_yoy"),
                "gross_margin": _v("gross_margin"),
            }
    _FUND_MAP = out
    _FUND_MTIME = path.stat().st_mtime if path.exists() else None
    return out


def load_name_map() -> dict[str, str]:
    path = CACHE_DIR / "names.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    try:
        spot = load_spot()
        mapping = dict(zip(spot["symbol"].astype(str), spot["name"].astype(str)))
        path.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
        return mapping
    except Exception:
        return {code: name for code, name in FALLBACK_UNIVERSE}


def stock_name(symbol: str) -> str:
    symbol = normalize_symbol(symbol)
    names = load_name_map()
    return names.get(symbol, symbol)


def is_st(name: str) -> bool:
    n = str(name).replace(" ", "").replace("＊", "*").upper()
    return "ST" in n


def is_main_board(symbol: str) -> bool:
    s = normalize_symbol(symbol)
    return s.startswith(MAIN_BOARD_PREFIXES)


def build_low20_universe(max_price: float = LOW_PRICE_MAX, refresh_spot: bool = True) -> list[dict]:
    """Main-board names with last price <= max_price, excluding STAR / ChiNext / ST."""
    spot = load_spot(refresh=refresh_spot)
    members = []
    for row in spot.itertuples():
        code = normalize_symbol(str(row.symbol))
        name = str(getattr(row, "name", "") or "")
        price = getattr(row, "price", None)
        try:
            price_f = float(price)
        except (TypeError, ValueError):
            continue
        if not is_main_board(code):
            continue
        if is_st(name):
            continue
        if not (0 < price_f <= max_price):
            continue
        members.append({"symbol": code, "name": name, "price": round(price_f, 3)})
    members.sort(key=lambda m: m["symbol"])
    meta = {
        "built_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "max_price": max_price,
        "count": len(members),
        "filters": ["主板", f"价格≤{max_price}", "剔除科创板688", "剔除创业板300/301", "剔除ST"],
    }
    (CACHE_DIR / "universe_low20.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (CACHE_DIR / "universe_low20.json").write_text(
        json.dumps(members, ensure_ascii=False), encoding="utf-8"
    )
    return members


def load_universe(key: str = "hs300", refresh: bool = False) -> list[dict]:
    key = key.lower()
    if key in ("low20", "cheap", "under20"):
        path = CACHE_DIR / "universe_low20.json"
        if path.exists() and not refresh:
            return json.loads(path.read_text(encoding="utf-8"))
        return build_low20_universe(refresh_spot=True)

    path = CACHE_DIR / f"universe_{key}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))

    if key in ("demo", "core", "sample"):
        members = [{"symbol": c, "name": n} for c, n in FALLBACK_UNIVERSE]
        path.write_text(json.dumps(members, ensure_ascii=False), encoding="utf-8")
        return members

    names = load_name_map()
    members: list[dict] = []
    if key in INDEX_UNIVERSES:
        index_code, _ = INDEX_UNIVERSES[key]
        try:
            import akshare as ak

            df = None
            for fn in (
                lambda: ak.index_stock_cons_csindex(symbol=index_code),
                lambda: ak.index_stock_cons(symbol=index_code),
            ):
                try:
                    df = fn()
                    if df is not None and not df.empty:
                        break
                except Exception:
                    continue
            if df is not None and not df.empty:
                code_col = None
                name_col = None
                for c in df.columns:
                    if "代码" in str(c) or str(c).lower() in ("code", "symbol", "con_code"):
                        code_col = c
                        break
                for c in df.columns:
                    if "名称" in str(c) or str(c).lower() in ("name", "con_name"):
                        name_col = c
                        break
                if code_col:
                    for _, row in df.iterrows():
                        code = normalize_symbol(str(row[code_col]).replace(".SH", "").replace(".SZ", "").split(".")[0])
                        if not code.isdigit():
                            continue
                        nm = str(row[name_col]) if name_col else names.get(code, code)
                        members.append({"symbol": code, "name": nm})
        except Exception:
            members = []

    if not members:
        members = [{"symbol": c, "name": n} for c, n in FALLBACK_UNIVERSE]

    # Deduplicate
    seen = set()
    uniq = []
    for m in members:
        if m["symbol"] in seen:
            continue
        seen.add(m["symbol"])
        uniq.append(m)

    path.write_text(json.dumps(uniq, ensure_ascii=False), encoding="utf-8")
    return uniq


def prefetch_universe(key: str = "hs300", start_date: str | None = None, progress: dict | None = None) -> dict:
    """Download bars for an index universe. `progress` is mutated for status polling."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    members = load_universe(key, refresh=(key in ("low20", "cheap", "under20")))
    start = _compact(start_date) or DEFAULT_START
    total = len(members)
    if progress is not None:
        progress.update({"status": "running", "done": 0, "total": total, "key": key})

    errors = []

    def _one(item):
        load_bars(item["symbol"], start, _today())
        return item["symbol"]

    done = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(_one, m): m for m in members}
        for fut in as_completed(futs):
            done += 1
            if progress is not None:
                progress["done"] = done
            try:
                fut.result()
            except Exception as exc:
                errors.append(f"{futs[fut]['symbol']}: {exc}")

    result = {"status": "done", "done": done, "total": total, "errors": errors[:12], "key": key}
    if progress is not None:
        progress.update(result)
    return result
