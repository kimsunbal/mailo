"""Claude Code hook entry point and wiring.

**`mailo hook` is a single entry point.** It branches on `hook_event_name` from
the stdin JSON, so there is no per-hook script and every settings.json entry ends
up being the same command.

Non-negotiables of the hook contract (DESIGN.md §5.1):

- **Always exit 0.** Every failure is swallowed. Exit 2 blocks the session, and a
  notifier must never emit it. Errors go to the log and nowhere else.
- **`async: true` with an explicit `timeout`**, so a network POST never holds the
  session.
- **Exec form** (`command` plus `args`) — no shell tokenisation, so paths with
  spaces are safe.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Final

from mailo import notify, state
from mailo.config import load
from mailo.events import Event
from mailo.log import get as get_logger

HOOK_ENTRY: Final[dict[str, Any]] = {
    "type": "command",
    "command": "mailo",
    "args": ["hook"],
    "async": True,
    "timeout": 30,
}

NOTIFICATION_MATCHER: Final = "permission_prompt|idle_prompt|agent_needs_input|agent_completed"

#: `notification_type` on a `Notification` hook, mapped to an event.
_NOTIFICATION_EVENTS: Final[dict[str, Event]] = {
    "permission_prompt": Event.BLOCKED,
    "agent_needs_input": Event.BLOCKED,
    "idle_prompt": Event.BLOCKED,
    "agent_completed": Event.DONE,
}

#: Hook name -> which event it represents. `None` means **send nothing**.
#:
#: `SessionStart` is that case: it exists only to cache `session_id -> cwd` in the
#: state file. It is easy to forget that one hook maps to no event, so the branch
#: table says so explicitly.
_HOOK_EVENTS: Final[dict[str, Event | None]] = {
    "SessionStart": None,
    "Notification": Event.BLOCKED,  # refined further by notification_type
    "StopFailure": Event.FAILED,
    "SessionEnd": Event.DONE,
    "Stop": Event.DONE,
}


def run() -> int:
    """The hook entry point. **Returns 0 no matter what happens.**"""
    log = get_logger()
    try:
        raw = sys.stdin.read()
    except Exception:
        return 0

    try:
        payload = json.loads(raw or "{}")
        if not isinstance(payload, dict):
            payload = {}
    except ValueError:
        log.warning("hook input was not JSON: %s", (raw or "")[:200])
        return 0

    try:
        _handle(payload)
    except Exception:
        log.exception("exception while handling hook — swallowed")
    return 0


def _handle(payload: dict[str, Any]) -> None:
    log = get_logger()
    hook_name = str(payload.get("hook_event_name") or "")
    session_id = str(payload.get("session_id") or "")
    cwd = payload.get("cwd")

    log.debug("hook received: %s", hook_name)

    # SessionStart sends nothing. Caching the cwd is all it does.
    if hook_name == "SessionStart":
        if cwd:
            state.remember_session(session_id, str(cwd))
        return

    if hook_name not in _HOOK_EVENTS:
        log.debug("unmapped hook: %s", hook_name)
        return

    event = _resolve_event(hook_name, payload)
    if event is None:
        return

    cfg = load(require=False)
    if not cfg.data:
        log.info("no configuration, not sending — run `mailo init`")
        return

    if hook_name == "Stop" and not _stop_enabled(cfg, payload):
        return

    # `blocked` can be delayed. With no resolution signal available, wait for a
    # second observation instead.
    if event is Event.BLOCKED:
        delay = int(cfg.triggers.get("blocked_delay_sec", 0))
        if not state.seen_blocked(session_id, delay):
            log.info("blocked observed — will send if seen again after %ds", delay)
            return
    else:
        state.clear_blocked(session_id)

    resolved_cwd = str(cwd) if cwd else state.recall_cwd(session_id)
    project = Path(resolved_cwd).name if resolved_cwd else "?"

    title = f"[{cfg.machine}] {project} — {event.label}"
    body = _body(cfg, payload)
    meta = notify.build_meta(cfg, cwd=resolved_cwd, extra=_extra(payload))

    results = notify.dispatch(
        cfg, notify.Notification(event, title, body, meta, session_id)
    )
    log.info("hook %s -> %s: %s", hook_name, event, notify.describe(results))


def _resolve_event(hook_name: str, payload: dict[str, Any]) -> Event | None:
    if hook_name != "Notification":
        return _HOOK_EVENTS[hook_name]

    kind = str(payload.get("notification_type") or "").strip()
    if not kind:
        # The field may simply be absent (§10 Q5 — not measured yet).
        return Event.BLOCKED
    event = _NOTIFICATION_EVENTS.get(kind)
    if event is None:
        get_logger().debug("unknown notification_type: %s", kind)
    return event


def _stop_enabled(cfg: Any, payload: dict[str, Any]) -> bool:
    """`Stop` fires every turn — opt-in only, and only for long enough turns.

    The one failure mode of a notifier is being noisy. With the key absent the
    hook is never registered in the first place, but leftover settings could
    still invoke it, so this blocks it here too.
    """
    threshold = cfg.triggers.get("stop_min_duration_sec")
    if not threshold:
        return False
    duration = payload.get("duration_sec") or payload.get("turn_duration_sec")
    return bool(duration and float(duration) >= float(threshold))


def _body(cfg: Any, payload: dict[str, Any]) -> str:
    """The notification body.

    **The default leaks nothing.** Conversation text only appears once
    `include_message_text` is on, and even then it is cut at 200 characters.
    """
    if not cfg.triggers.get("include_message_text"):
        return ""
    text = str(payload.get("notification_text") or payload.get("message") or "").strip()
    return text[:200] + ("…" if len(text) > 200 else "")


def _extra(payload: dict[str, Any]) -> dict[str, str]:
    extra: dict[str, str] = {}
    kind = payload.get("notification_type")
    if kind:
        extra["type"] = str(kind)
    reason = payload.get("reason")
    if reason:
        extra["reason"] = str(reason)
    return extra


# ── wiring ──────────────────────────────────────────────────────────────────


def settings_path(scope: str) -> Path:
    if scope == "project":
        return Path.cwd() / ".claude" / "settings.json"
    return Path.home() / ".claude" / "settings.json"


def _matchers(events: list[str] | None) -> dict[str, str]:
    """Which hooks to register, and with what matcher.

    **`SessionStart` is registered regardless of `--events`.** Leaving it out
    strips the project name from `blocked` notifications.
    """
    wanted = set(events) if events else {e.value for e in Event}
    wiring: dict[str, str] = {"SessionStart": "*"}
    if wanted & {"blocked", "done"}:
        wiring["Notification"] = NOTIFICATION_MATCHER
    if "failed" in wanted:
        wiring["StopFailure"] = "*"
    if "done" in wanted:
        wiring["SessionEnd"] = "*"
    return wiring


def install(scope: str = "user", events: list[str] | None = None) -> tuple[Path, list[str]]:
    """Merge into the `hooks` key of settings.json, preserving existing hooks."""
    path = settings_path(scope)
    settings = _read_settings(path)
    hooks = settings.setdefault("hooks", {})

    # Strip **every** existing mailo entry before adding the new ones. Otherwise
    # re-installing with a narrower --events leaves the previous hooks in place
    # and they keep firing.
    for hook_name in list(hooks):
        entries = hooks[hook_name]
        if not isinstance(entries, list):
            continue
        kept = [e for e in entries if not _is_mailo(e)]
        if kept:
            hooks[hook_name] = kept
        else:
            del hooks[hook_name]

    installed: list[str] = []
    for hook_name, matcher in _matchers(events).items():
        entries = hooks.setdefault(hook_name, [])
        entries.append({"matcher": matcher, "hooks": [dict(HOOK_ENTRY)]})
        installed.append(hook_name)

    _write_settings(path, settings)
    return path, installed


def uninstall(scope: str = "user") -> tuple[Path, int]:
    """Remove only mailo's entries; leave everyone else's hooks alone."""
    path = settings_path(scope)
    if not path.exists():
        return path, 0

    settings = _read_settings(path)
    hooks = settings.get("hooks") or {}
    removed = 0
    for hook_name in list(hooks):
        entries = hooks[hook_name]
        if not isinstance(entries, list):
            continue
        kept = [e for e in entries if not _is_mailo(e)]
        removed += len(entries) - len(kept)
        if kept:
            hooks[hook_name] = kept
        else:
            del hooks[hook_name]

    if not hooks:
        settings.pop("hooks", None)
    if removed:
        _write_settings(path, settings)
    return path, removed


def installed_hooks(scope: str = "user") -> list[str]:
    hooks = (_read_settings(settings_path(scope)).get("hooks") or {}).items()
    return sorted(name for name, entries in hooks if any(_is_mailo(e) for e in entries or []))


def _is_mailo(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    for hook in entry.get("hooks") or []:
        if not isinstance(hook, dict):
            continue
        command = str(hook.get("command") or "")
        if Path(command).name == "mailo" or command.endswith("-m mailo"):
            return True
    return False


def _read_settings(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_settings(path: Path, settings: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp{os.getpid()}")
    tmp.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)
