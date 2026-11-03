"""Theme / report / major-event calendar with optional live news enrichment."""

from __future__ import annotations

import calendar as pycal
import json
import re
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

SEED_PATH = Path(__file__).resolve().parent / "data" / "calendar_seed.json"

THEME_KEYWORDS = (
    "两会",
    "政治局",
    "中央经济工作",
    "国务院",
    "央行",
    "降准",
    "降息",
    "稳增长",
    "新能源",
    "半导体",
    "人工智能",
    "低空经济",
    "消费",
    "地产",
    "财报",
    "年报",
    "季报",
)


@lru_cache(maxsize=1)
def _load_seed() -> dict[str, Any]:
    raw = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    return raw


def _parse_date(s: str) -> date:
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


def _month_info(seed: dict, month: int) -> dict:
    m = seed.get("months", {}).get(str(month)) or seed.get("months", {}).get(month) or {}
    return {
        "month": month,
        "themes": list(m.get("themes") or []),
        "note": m.get("note") or "",
    }


def _report_windows_for_month(seed: dict, month: int) -> list[dict]:
    out = []
    for w in seed.get("report_windows") or []:
        if month in (w.get("months") or []):
            out.append(
                {
                    "id": w.get("id"),
                    "name": w.get("name"),
                    "peak": w.get("peak"),
                    "note": w.get("note"),
                }
            )
    return out


def _events_on_day(seed: dict, year: int, d: date) -> list[dict]:
    hits = []
    for ev in seed.get("events") or []:
        if (ev.get("recur") or "annual") != "annual":
            continue
        if int(ev.get("month") or 0) != d.month:
            continue
        a = int(ev.get("day_start") or 1)
        b = int(ev.get("day_end") or a)
        # clamp to month length
        last = pycal.monthrange(year, d.month)[1]
        a = max(1, min(a, last))
        b = max(a, min(b, last))
        if a <= d.day <= b:
            hits.append(
                {
                    "id": ev.get("id"),
                    "title": ev.get("title"),
                    "level": ev.get("level") or "normal",
                    "themes": list(ev.get("themes") or []),
                    "note": ev.get("note") or "",
                    "source": "builtin",
                }
            )
    return hits


def _day_flags(events: list[dict], reports: list[dict]) -> dict:
    major = any(e.get("level") == "major" for e in events)
    return {
        "has_event": bool(events),
        "has_major": major,
        "has_report": bool(reports),
    }


def fetch_live_events(day: date, limit: int = 12) -> list[dict]:
    """Best-effort live headlines; returns [] on any failure."""
    items: list[dict] = []
    day_s = day.strftime("%Y-%m-%d")
    day_compact = day.strftime("%Y%m%d")

    # 1) East Money flash news — filter by date prefix
    try:
        import akshare as ak

        df = ak.stock_info_global_em()
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                title = str(row.get("标题") or "")
                summary = str(row.get("摘要") or "")
                ts = str(row.get("发布时间") or "")
                if not title:
                    continue
                if not (ts.startswith(day_s) or day_s in ts):
                    # keep recent if same calendar day unavailable — skip mismatched days
                    continue
                text = title + summary
                themes = [k for k in THEME_KEYWORDS if k in text][:4]
                items.append(
                    {
                        "title": title,
                        "note": summary[:180],
                        "level": "major" if any(k in text for k in ("两会", "政治局", "中央经济工作", "降准", "降息")) else "normal",
                        "themes": themes,
                        "source": "eastmoney",
                        "url": str(row.get("链接") or "") or None,
                    }
                )
                if len(items) >= limit:
                    break
    except Exception:
        pass

    # 2) CCTV news transcript titles for that day
    if len(items) < limit:
        try:
            import akshare as ak

            df = ak.news_cctv(date=day_compact)
            if df is not None and not df.empty:
                title_col = "title" if "title" in df.columns else df.columns[0]
                content_col = "content" if "content" in df.columns else None
                for _, row in df.head(limit).iterrows():
                    title = str(row.get(title_col) or "").strip()
                    if not title or len(title) < 4:
                        continue
                    note = str(row.get(content_col) or "")[:180] if content_col else ""
                    text = title + note
                    themes = [k for k in THEME_KEYWORDS if k in text][:4]
                    items.append(
                        {
                            "title": title,
                            "note": note,
                            "level": "major" if re.search(r"习近平|政治局|国务院|中央经济", text) else "normal",
                            "themes": themes,
                            "source": "cctv",
                        }
                    )
                    if len(items) >= limit:
                        break
        except Exception:
            pass

    # dedupe by title
    seen = set()
    out = []
    for it in items:
        t = it["title"]
        if t in seen:
            continue
        seen.add(t)
        out.append(it)
    return out[:limit]


def calendar_month(year: int, month: int, include_live: bool = False) -> dict[str, Any]:
    seed = _load_seed()
    year = int(year)
    month = int(month)
    if month < 1 or month > 12:
        raise ValueError("month must be 1..12")
    last = pycal.monthrange(year, month)[1]
    month_meta = _month_info(seed, month)
    reports = _report_windows_for_month(seed, month)

    days = []
    for d in range(1, last + 1):
        day = date(year, month, d)
        events = _events_on_day(seed, year, day)
        flags = _day_flags(events, reports if d >= 1 else [])
        # report flag only meaningful if we're inside a report month — mark peak end days stronger
        days.append(
            {
                "date": day.isoformat(),
                "day": d,
                "weekday": day.weekday(),  # Mon=0
                "events": events,
                "flags": flags,
            }
        )

    payload = {
        "year": year,
        "month": month,
        "month_themes": month_meta,
        "report_windows": reports,
        "days": days,
        "disclaimer": seed.get("disclaimer") or "",
        "live_available": False,
        "live_events_sample": [],
    }

    if include_live:
        # sample live for today if in this month, else month mid
        today = date.today()
        sample_day = today if (today.year == year and today.month == month) else date(year, month, min(15, last))
        live = fetch_live_events(sample_day, limit=8)
        payload["live_available"] = bool(live)
        payload["live_events_sample"] = live
        payload["live_sample_date"] = sample_day.isoformat()

    return payload


def calendar_day(day_str: str, include_live: bool = True) -> dict[str, Any]:
    seed = _load_seed()
    d = _parse_date(day_str)
    month_meta = _month_info(seed, d.month)
    reports = _report_windows_for_month(seed, d.month)
    events = _events_on_day(seed, d.year, d)
    live: list[dict] = []
    if include_live:
        live = fetch_live_events(d, limit=12)

    # nearby majors within ±5 days
    nearby = []
    for delta in range(-5, 6):
        if delta == 0:
            continue
        nd = d + timedelta(days=delta)
        for ev in _events_on_day(seed, nd.year, nd):
            if ev.get("level") == "major":
                nearby.append({**ev, "date": nd.isoformat(), "offset": delta})

    return {
        "date": d.isoformat(),
        "weekday": d.weekday(),
        "month_themes": month_meta,
        "report_windows": reports,
        "events": events,
        "live_events": live,
        "nearby_major": nearby[:8],
        "flags": {
            **_day_flags(events, reports),
            "has_live": bool(live),
        },
        "disclaimer": seed.get("disclaimer") or "",
    }
