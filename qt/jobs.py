"""Daily cache refresh plus a manual trigger. Times are local (Asia/Shanghai on this machine)."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from typing import Any

from qt.alerts import load_alerts, scan_alerts
from qt.config import CACHE_DIR, DEFAULT_START
from qt.dashboard import build_dashboard
from qt.data import list_cached_symbols, load_bars, load_universe

STATE_PATH = CACHE_DIR / "job_state.json"
UPDATE_HOUR = 16
UPDATE_MINUTE = 30

_lock = threading.Lock()
progress: dict[str, Any] = {
    "status": "idle",
    "phase": None,
    "done": 0,
    "total": 0,
    "key": "low20",
    "reason": None,
}
_stop = threading.Event()
_started = False


def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_state(patch: dict) -> dict:
    state = _load_state()
    state.update(patch)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state


def _next_run_at(now: datetime | None = None) -> str:
    now = now or datetime.now()
    target = now.replace(hour=UPDATE_HOUR, minute=UPDATE_MINUTE, second=0, microsecond=0)
    if now.weekday() >= 5:
        days = 7 - now.weekday()
        target = (now + timedelta(days=days)).replace(hour=UPDATE_HOUR, minute=UPDATE_MINUTE, second=0, microsecond=0)
    elif now >= target:
        nxt = now + timedelta(days=1)
        while nxt.weekday() >= 5:
            nxt += timedelta(days=1)
        target = nxt.replace(hour=UPDATE_HOUR, minute=UPDATE_MINUTE, second=0, microsecond=0)
    return target.strftime("%Y-%m-%d %H:%M")


def status() -> dict:
    state = _load_state()
    alerts = load_alerts()
    return {
        **progress,
        "last_success": state.get("last_success"),
        "last_reason": state.get("last_reason"),
        "next_run": _next_run_at(),
        "schedule": f"每个交易日 {UPDATE_HOUR:02d}:{UPDATE_MINUTE:02d}",
        "cached": len(list_cached_symbols()),
        "alert_buys": len(alerts.get("buys") or []),
        "alert_sells": len(alerts.get("sells") or []),
        "alerts_at": alerts.get("scanned_at"),
    }


def _run_update(universe: str, reason: str) -> None:
    progress.update(
        {
            "status": "running",
            "phase": "bars",
            "done": 0,
            "total": 0,
            "key": universe,
            "reason": reason,
            "error": None,
        }
    )
    _save_state({"status": "running", "started_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "reason": reason})
    try:
        rebuild = reason in ("manual", "daily")
        members = load_universe(universe, refresh=rebuild)
        if list_cached_symbols() and reason in ("resume", "daily", "manual"):
            progress["phase"] = "alerts"
            try:
                scan_alerts(universe, progress=progress)
            except Exception:
                pass
        cached = set(list_cached_symbols())
        extra = [{"symbol": s, "name": s} for s in cached if s not in {m["symbol"] for m in members}]
        # Prefer universe members; still bump already-cached names to latest.
        from concurrent.futures import ThreadPoolExecutor, as_completed

        jobs = members + extra
        total = len(jobs)
        progress.update({"total": total, "done": 0, "phase": "bars"})

        errors = []

        def _one(item):
            load_bars(item["symbol"], DEFAULT_START, None)
            return item["symbol"]

        done = 0
        with ThreadPoolExecutor(max_workers=8) as pool:
            futs = {pool.submit(_one, m): m for m in jobs}
            for fut in as_completed(futs):
                if _stop.is_set():
                    break
                done += 1
                progress["done"] = done
                try:
                    fut.result()
                except Exception as exc:
                    errors.append(f"{futs[fut]['symbol']}: {exc}")

        progress.update({"phase": "alerts", "errors": errors[:12]})
        alerts = scan_alerts(universe, progress=progress)
        progress.update({"phase": "sectors"})
        try:
            from qt.sectors import ensure_sectors

            ensure_sectors(force=True, progress=progress)
        except Exception:
            pass
        progress.update({"phase": "dashboard"})
        try:
            build_dashboard(universe, progress=progress)
        except Exception:
            pass
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        progress.update(
            {
                "status": "done",
                "phase": None,
                "done": done,
                "total": total,
                "alert_buys": len(alerts.get("buys") or []),
                "alert_sells": len(alerts.get("sells") or []),
            }
        )
        _save_state(
            {
                "status": "done",
                "last_success": now,
                "last_reason": reason,
                "last_errors": errors[:12],
            }
        )
    except Exception as exc:
        progress.update({"status": "error", "error": str(exc), "phase": None})
        _save_state({"status": "error", "last_error": str(exc)})


def start_update(universe: str = "low20", reason: str = "manual") -> dict:
    with _lock:
        if progress.get("status") == "running":
            return status()
        progress["status"] = "running"
        threading.Thread(target=_run_update, args=(universe, reason), daemon=True).start()
    return {"status": "started", "reason": reason, "key": universe}


def _due(now: datetime, last_success: str | None) -> bool:
    if now.weekday() >= 5:
        return False
    if now.hour < UPDATE_HOUR or (now.hour == UPDATE_HOUR and now.minute < UPDATE_MINUTE):
        return False
    if not last_success:
        return True
    try:
        last = datetime.strptime(last_success, "%Y-%m-%d %H:%M")
    except ValueError:
        return True
    return last.date() < now.date()


def scheduler_loop() -> None:
    while not _stop.is_set():
        try:
            st = _load_state()
            if progress.get("status") != "running" and _due(datetime.now(), st.get("last_success")):
                start_update("low20", "daily")
        except Exception:
            pass
        _stop.wait(60)


def start_scheduler() -> None:
    global _started
    if _started:
        return
    _started = True
    state = _load_state()
    cached = list_cached_symbols()
    try:
        universe = load_universe("low20", refresh=False)
    except Exception:
        universe = []
    interrupted = state.get("status") == "running" or (
        universe and cached and len(cached) < int(len(universe) * 0.9) and not state.get("last_success")
    )
    if interrupted:
        start_update("low20", "resume")
    elif cached and not (CACHE_DIR / "alerts.json").exists():
        def _boot_scan():
            try:
                scan_alerts("low20", progress=progress)
                try:
                    build_dashboard("low20", progress=progress)
                except Exception:
                    pass
                if universe and len(cached) >= int(len(universe) * 0.9):
                    _save_state(
                        {
                            "status": "done",
                            "last_success": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "last_reason": "boot-scan",
                        }
                    )
            except Exception:
                pass

        threading.Thread(target=_boot_scan, daemon=True).start()
    elif cached and not (CACHE_DIR / "dashboard.json").exists():
        def _boot_dash():
            try:
                build_dashboard("low20", progress=progress)
            except Exception:
                pass

        threading.Thread(target=_boot_dash, daemon=True).start()
    threading.Thread(target=scheduler_loop, daemon=True).start()


# Keep an alias so existing prefetch callers can share the same progress dict.
def prefetch_with_progress(universe: str = "low20") -> dict:
    return start_update(universe, "manual")
