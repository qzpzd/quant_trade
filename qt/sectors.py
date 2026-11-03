"""Industry / concept maps from 巨潮资料 + 申万三级（可用时），落盘本地。"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

from qt.config import CACHE_DIR
from qt.data import list_cached_symbols, normalize_symbol

SECTORS_PATH = CACHE_DIR / "sectors.json"
MAX_CONCEPTS_PER_STOCK = 8
_lock = threading.Lock()
_building = False

SKIP_INDEX = {
    "沪深300",
    "中证500",
    "中证1000",
    "上证50",
    "上证指数",
    "深证成指",
    "创业板指",
    "科创50",
    "中证800",
    "中证A500",
}


def _empty() -> dict[str, Any]:
    return {
        "built_at": None,
        "source": None,
        "industry_of": {},
        "concepts_of": {},
        "industry_names": [],
        "concept_names": [],
    }


def load_sectors() -> dict[str, Any]:
    if not SECTORS_PATH.exists():
        return _empty()
    try:
        data = json.loads(SECTORS_PATH.read_text(encoding="utf-8"))
        data.setdefault("industry_of", {})
        data.setdefault("concepts_of", {})
        data.setdefault("industry_names", [])
        data.setdefault("concept_names", [])
        return data
    except Exception:
        return _empty()


def _save(payload: dict[str, Any]) -> None:
    SECTORS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SECTORS_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def lookup_sectors(symbol: str, data: dict[str, Any] | None = None) -> tuple[str, list[str]]:
    data = data or load_sectors()
    code = normalize_symbol(symbol)
    industry = data.get("industry_of", {}).get(code) or "未分类"
    concepts = list(data.get("concepts_of", {}).get(code) or [])[:MAX_CONCEPTS_PER_STOCK]
    return industry, concepts


def _code_col(df) -> str | None:
    for c in ("股票代码", "代码", "证券代码", "code"):
        if c in df.columns:
            return c
    return None


def _split_tags(raw: Any) -> list[str]:
    if raw is None:
        return []
    s = str(raw).strip()
    if not s or s in ("None", "nan"):
        return []
    out = []
    for part in s.replace("，", ",").replace("、", ",").replace(";", ",").replace("；", ",").split(","):
        p = part.strip()
        if not p or len(p) > 24 or p in SKIP_INDEX:
            continue
        if "ESG" in p.upper() or p.endswith("指数") or p.endswith("指"):
            continue
        if any(x in p for x in ("沪深", "中证", "上证", "深证", "创业板", "科创", "中小100", "中小300")):
            continue
        out.append(p)
    return out


def _profile_one(code: str) -> tuple[str, str | None, list[str]]:
    import akshare as ak

    try:
        df = ak.stock_profile_cninfo(symbol=code)
    except Exception:
        time.sleep(0.2)
        try:
            df = ak.stock_profile_cninfo(symbol=code)
        except Exception:
            return code, None, []
    if df is None or df.empty:
        return code, None, []
    row = df.iloc[0]
    ind = None
    concepts: list[str] = []
    for c in df.columns:
        name = str(c)
        val = row[c]
        if ind is None and "行业" in name:
            v = str(val).strip() if val is not None else ""
            if v and v not in ("None", "nan"):
                ind = v
        if "指数" in name or "概念" in name or "板块" in name:
            concepts.extend(_split_tags(val))
    # 主营业务关键词弱标签（短词）
    for c in df.columns:
        if "主营" in str(c):
            text = str(row[c] or "")
            for kw in ("半导体", "锂电", "光伏", "军工", "医药", "白酒", "银行", "证券", "保险", "房地产", "人工智能", "新能源", "芯片", "算力", "机器人"):
                if kw in text and kw not in concepts:
                    concepts.append(kw)
    # dedupe
    seen = set()
    uniq = []
    for x in concepts:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return code, ind, uniq[:MAX_CONCEPTS_PER_STOCK]


def _fetch_cninfo_maps(symbols: list[str], progress: dict | None = None) -> tuple[dict[str, str], dict[str, list[str]]]:
    industry_of: dict[str, str] = {}
    concepts_of: dict[str, list[str]] = {}
    total = len(symbols)
    if progress is not None:
        progress.update({"phase": "sectors", "scan_done": 0, "scan_total": total, "sectors_msg": "巨潮行业概念"})

    done = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(_profile_one, c) for c in symbols]
        for fut in as_completed(futs):
            code, ind, cons = fut.result()
            done += 1
            if ind:
                industry_of[code] = ind
            if cons:
                concepts_of[code] = cons
            elif ind:
                concepts_of[code] = [ind]
            if progress is not None and (done % 20 == 0 or done == total):
                progress["scan_done"] = done
            if done % 80 == 0:
                _save(
                    {
                        "built_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "source": "cninfo-partial",
                        "industry_of": dict(industry_of),
                        "concepts_of": {k: list(v) for k, v in concepts_of.items()},
                        "industry_names": sorted(set(industry_of.values())),
                        "concept_names": sorted({c for lst in concepts_of.values() for c in lst}),
                        "industry_count": len(industry_of),
                        "concept_stock_count": len(concepts_of),
                        "partial": True,
                    }
                )
    return industry_of, concepts_of


def _try_sw_overlay(industry_of: dict[str, str], concepts_of: dict[str, list[str]]) -> str | None:
    """可选叠加申万三级；失败返回 None。"""
    try:
        import akshare as ak

        info = ak.sw_index_third_info()
    except Exception:
        return None
    code_col = "行业代码" if "行业代码" in info.columns else info.columns[0]
    name_col = "行业名称" if "行业名称" in info.columns else info.columns[1]
    parent_col = "上级行业" if "上级行业" in info.columns else None
    rows = []
    for _, r in info.iterrows():
        code = str(r[code_col])
        if not code.endswith(".SI"):
            code = f"{code}.SI"
        rows.append((code, str(r[name_col]), str(r[parent_col]) if parent_col else ""))

    def _one(item):
        sw_code, ind_name, parent = item
        try:
            import akshare as ak

            cons = ak.sw_index_third_cons(symbol=sw_code)
            col = _code_col(cons)
            if col is None or cons is None or cons.empty:
                return ind_name, parent, []
            codes = []
            for x in cons[col].tolist():
                c = normalize_symbol(str(x).split(".")[0])
                if c:
                    codes.append(c)
            return ind_name, parent, codes
        except Exception:
            return ind_name, parent, []

    hit = 0
    with ThreadPoolExecutor(max_workers=3) as pool:
        futs = [pool.submit(_one, row) for row in rows]
        for fut in as_completed(futs):
            ind_name, parent, codes = fut.result()
            if not codes:
                continue
            hit += 1
            for c in codes:
                # 申万更细时覆盖巨潮粗行业
                industry_of[c] = ind_name
                lst = concepts_of.setdefault(c, [])
                for tag in (parent, ind_name):
                    if tag and tag not in lst and len(lst) < MAX_CONCEPTS_PER_STOCK:
                        lst.append(tag)
    return f"sw3:{hit}" if hit else None


def refresh_sectors(progress: dict | None = None) -> dict[str, Any]:
    old = load_sectors()
    try:
        symbols = list_cached_symbols()
        if not symbols:
            raise RuntimeError("本地无缓存股票，请先更新缓存")
        industry_of, concepts_of = _fetch_cninfo_maps(symbols, progress=progress)
        sw_tag = _try_sw_overlay(industry_of, concepts_of)
        industry_names = sorted(set(industry_of.values()))
        concept_names = sorted({c for lst in concepts_of.values() for c in lst})
        source = "cninfo"
        if sw_tag:
            source = f"cninfo+{sw_tag}"
        payload = {
            "built_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "source": source,
            "industry_of": industry_of,
            "concepts_of": concepts_of,
            "industry_names": industry_names,
            "concept_names": concept_names,
            "industry_count": len(industry_of),
            "concept_stock_count": len(concepts_of),
            "partial": False,
        }
        _save(payload)
        return payload
    except Exception as exc:
        cur = load_sectors()
        if cur.get("built_at"):
            cur["warning"] = str(exc)
            return cur
        if old.get("built_at"):
            old["warning"] = str(exc)
            return old
        raise


def ensure_sectors(force: bool = False, progress: dict | None = None) -> dict[str, Any]:
    data = load_sectors()
    if data.get("built_at") and not force and len(data.get("industry_of") or {}) > 500:
        return data
    with _lock:
        data = load_sectors()
        if data.get("built_at") and not force and len(data.get("industry_of") or {}) > 500:
            return data
        return refresh_sectors(progress=progress)


def ensure_sectors_async(force: bool = False) -> None:
    global _building
    data = load_sectors()
    if data.get("built_at") and not force and len(data.get("industry_of") or {}) > 500:
        return
    with _lock:
        if _building and not force:
            return
        _building = True

    def _run():
        global _building
        try:
            refresh_sectors()
        except Exception:
            pass
        finally:
            _building = False

    threading.Thread(target=_run, daemon=True).start()


def sectors_status() -> dict[str, Any]:
    data = load_sectors()
    return {
        "built_at": data.get("built_at"),
        "source": data.get("source"),
        "building": _building,
        "partial": data.get("partial"),
        "industry_count": len(data.get("industry_of") or {}),
        "concept_stock_count": len(data.get("concepts_of") or {}),
        "industry_names": data.get("industry_names") or [],
        "concept_names": (data.get("concept_names") or [])[:120],
        "warning": data.get("warning"),
    }


def fetch_limit_up_codes(as_of: str | None = None) -> set[str]:
    import akshare as ak

    day = (as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")[:8]
    try:
        df = ak.stock_zt_pool_em(date=day)
    except Exception:
        return set()
    if df is None or df.empty:
        return set()
    col = _code_col(df) or ("代码" if "代码" in df.columns else None)
    if not col:
        return set()
    return {normalize_symbol(str(x)) for x in df[col].tolist() if x}


def limit_up_threshold(symbol: str, name: str | None = None) -> float:
    s = normalize_symbol(symbol)
    nm = (name or "").upper()
    if "ST" in nm:
        return 4.7
    if s.startswith(("300", "301", "688")):
        return 19.7
    return 9.7


def is_limit_up_by_pct(symbol: str, pct_chg: float | None, name: str | None = None) -> bool:
    if pct_chg is None:
        return False
    return float(pct_chg) >= limit_up_threshold(symbol, name)
