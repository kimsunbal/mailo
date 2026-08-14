"""State file — `$XDG_STATE_HOME/mailo/state.json`.

Three things are remembered.

1. **`session_id -> cwd`.** The `Notification` hook has no `cwd`. Without caching
   it from `SessionStart`, `blocked` notifications lose the project name
   (DESIGN.md §5.2).
2. **Cooldown**, to suppress repeats of the same (session, event).
3. **Daily volume**, for the SMTP cap. Exceeding Gmail's 500/day locks the user's
   *real* mail account for up to 24 hours — not mailo's problem to shrug at.

This module **never raises.** It runs on the hook path, and a notifier's state
file must not be able to break a session. On failure it degrades to empty state.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from mailo.config import state_dir

_SESSION_TTL = 7 * 24 * 3600  # drop stale session cache entries


def _path() -> Path:
    return state_dir() / "state.json"


def load() -> dict[str, Any]:
    try:
        return json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(data: dict[str, Any]) -> None:
    path = _path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.tmp{os.getpid()}")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass  # failing to persist state must not stop the notification


def _prune(data: dict[str, Any], now: float) -> None:
    sessions = data.get("sessions") or {}
    for sid in [s for s, v in sessions.items() if now - v.get("ts", 0) > _SESSION_TTL]:
        sessions.pop(sid, None)
    data["sessions"] = sessions


# ── session context ─────────────────────────────────────────────────────────


def remember_session(session_id: str, cwd: str) -> None:
    if not session_id or not cwd:
        return
    data = load()
    now = time.time()
    _prune(data, now)
    data.setdefault("sessions", {})[session_id] = {"cwd": cwd, "ts": now}
    save(data)


def recall_cwd(session_id: str) -> str | None:
    if not session_id:
        return None
    entry = (load().get("sessions") or {}).get(session_id)
    return entry.get("cwd") if entry else None


# ── cooldown ────────────────────────────────────────────────────────────────


def cooled_down(session_id: str, event: str, window: int) -> bool:
    """Whether this send clears the cooldown; stamps the time if it does.

    Checking and stamping live in one function because splitting them means a
    caller eventually forgets to stamp.
    """
    if window <= 0:
        return True
    key = f"{session_id or '-'}:{event}"
    data = load()
    now = time.time()
    last = (data.get("cooldown") or {}).get(key, 0)
    if now - last < window:
        return False
    data.setdefault("cooldown", {})[key] = now
    save(data)
    return True


def seen_blocked(session_id: str, delay: int) -> bool:
    """Delayed `blocked` — has this session been seen blocked twice, `delay` apart?

    Hook input carries no "no longer blocked" signal (DESIGN.md §10 Q3). Rather
    than detecting resolution, this waits for **re-observation**: swallow the
    first notification, and send when a still-blocked session reports again.

    With `delay <= 0` it sends immediately, which is the v1 default.
    """
    if delay <= 0:
        return True
    key = session_id or "-"
    data = load()
    now = time.time()
    pending = data.setdefault("blocked_since", {})
    first = pending.get(key)
    if first is None:
        pending[key] = now
        save(data)
        return False
    if now - first >= delay:
        pending.pop(key, None)
        save(data)
        return True
    return False


def clear_blocked(session_id: str) -> None:
    """Any sign the session moved on clears the pending state."""
    data = load()
    if (data.get("blocked_since") or {}).pop(session_id or "-", None) is not None:
        save(data)


# ── daily cap ───────────────────────────────────────────────────────────────


def quota_ok(channel: str, limit: int) -> bool:
    """Whether today's volume is under the cap; increments it if so.

    Cooldown only covers one session, so it cannot catch several separate
    sessions each sending their own. This is the separate mechanism for that.
    """
    if limit <= 0:
        return True
    today = time.strftime("%Y-%m-%d")
    data = load()
    quota = data.setdefault("quota", {})
    entry = quota.get(channel)
    if not entry or entry.get("date") != today:
        entry = {"date": today, "count": 0}
    if entry["count"] >= limit:
        return False
    entry["count"] += 1
    quota[channel] = entry
    save(data)
    return True


def quota_used(channel: str) -> int:
    entry = (load().get("quota") or {}).get(channel)
    if not entry or entry.get("date") != time.strftime("%Y-%m-%d"):
        return 0
    return int(entry.get("count", 0))
