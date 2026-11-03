"""Named, deletable pattern templates and screen presets (dynamic / static)."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime

from qt.config import CACHE_DIR

PATTERNS_PATH = CACHE_DIR / "patterns.json"
SCREENS_PATH = CACHE_DIR / "screens.json"
_lock = threading.Lock()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _read(path) -> list[dict]:
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return raw if isinstance(raw, list) else []


def _write(path, items: list[dict]) -> list[dict]:
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return items


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def load_patterns() -> list[dict]:
    return _read(PATTERNS_PATH)


def get_pattern(pid: str) -> dict | None:
    for item in load_patterns():
        if item.get("id") == pid:
            return item
    return None


def save_pattern(item: dict) -> dict:
    with _lock:
        items = load_patterns()
        pid = item.get("id") or _new_id()
        item = {**item, "id": pid, "updated_at": _now()}
        item.setdefault("created_at", _now())
        items = [x for x in items if x.get("id") != pid]
        items.insert(0, item)
        _write(PATTERNS_PATH, items)
        return item


def delete_pattern(pid: str) -> dict:
    with _lock:
        items = [x for x in load_patterns() if x.get("id") != pid]
        _write(PATTERNS_PATH, items)
        return {"ok": True, "id": pid, "items": items}


def load_screens() -> list[dict]:
    return _read(SCREENS_PATH)


def get_screen(sid: str) -> dict | None:
    for item in load_screens():
        if item.get("id") == sid:
            return item
    return None


def save_screen(item: dict) -> dict:
    with _lock:
        items = load_screens()
        sid = item.get("id") or _new_id()
        item = {**item, "id": sid, "updated_at": _now()}
        item.setdefault("created_at", _now())
        items = [x for x in items if x.get("id") != sid]
        items.insert(0, item)
        _write(SCREENS_PATH, items)
        return item


def delete_screen(sid: str) -> dict:
    with _lock:
        items = [x for x in load_screens() if x.get("id") != sid]
        _write(SCREENS_PATH, items)
        return {"ok": True, "id": sid, "items": items}


def add_screen_hit(sid: str, hit: dict) -> dict:
    with _lock:
        items = load_screens()
        found = None
        code = str((hit or {}).get("symbol") or "")
        if not code:
            raise RuntimeError("缺少股票代码")
        for item in items:
            if item.get("id") != sid:
                continue
            if item.get("mode") != "static":
                raise RuntimeError("只有静态条件才能手动加入股票")
            hits = [h for h in (item.get("hits") or []) if str(h.get("symbol")) != code]
            hits.insert(0, hit)
            item["hits"] = hits
            item["count"] = len(hits)
            item["updated_at"] = _now()
            found = item
            break
        if found is None:
            raise RuntimeError("未找到该条件")
        _write(SCREENS_PATH, items)
        return found


def remove_screen_hit(sid: str, symbol: str) -> dict:
    with _lock:
        items = load_screens()
        found = None
        for item in items:
            if item.get("id") != sid:
                continue
            if item.get("mode") != "static":
                raise RuntimeError("只有静态条件才能删除其中的股票")
            hits = [h for h in (item.get("hits") or []) if str(h.get("symbol")) != str(symbol)]
            item["hits"] = hits
            item["count"] = len(hits)
            item["updated_at"] = _now()
            found = item
            break
        if found is None:
            raise RuntimeError("未找到该条件")
        _write(SCREENS_PATH, items)
        return found
