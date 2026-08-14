"""Delivery orchestration — routing, suppression, retries.

Channel adapters only know how to send. **When to send, how many times, and to
whom** is decided here.

The retry ceiling is **hard-coded and not exposed as a setting**, so no user can
raise it to a value that gets their own IP banned by Discord.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from mailo import channels, state
from mailo.config import Config
from mailo.errors import ChannelError, PermanentError, TransientError
from mailo.events import Event
from mailo.log import get as get_logger

MAX_ATTEMPTS: Final = 2  # first try plus one retry; not configurable
BACKOFF_SEC: Final = 2.0


@dataclass(frozen=True, slots=True)
class Result:
    channel: str
    sent: bool
    detail: str = ""

    @property
    def skipped(self) -> bool:
        return not self.sent and not self.detail.startswith("failed")


@dataclass(slots=True)
class Notification:
    """One notification to deliver."""

    event: Event
    title: str
    body: str = ""
    meta: dict[str, str] = field(default_factory=dict)
    session_id: str = ""


def build_meta(
    cfg: Config,
    *,
    cwd: str | None = None,
    elapsed: float | None = None,
    exit_code: int | None = None,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    """Metadata attached to a notification.

    **The default leaks nothing.** The directory *name* goes in, never the full
    path — `/home/someone/work/secret-project` is itself information.
    """
    meta: dict[str, str] = {"machine": cfg.machine}
    if cwd:
        meta["project"] = Path(cwd).name
    if elapsed is not None:
        meta["elapsed"] = _duration(elapsed)
    if exit_code is not None:
        meta["exit"] = str(exit_code)
    if extra:
        meta.update({k: v for k, v in extra.items() if v})
    return meta


def _duration(seconds: float) -> str:
    total = int(seconds)
    if total < 60:
        return f"{total}s"
    if total < 3600:
        return f"{total // 60}m {total % 60}s"
    return f"{total // 3600}h {(total % 3600) // 60}m"


def dispatch(
    cfg: Config,
    note: Notification,
    *,
    only: str | None = None,
    ignore_suppression: bool = False,
) -> list[Result]:
    """Send to the channels the routing table names.

    Each channel is attempted **independently**. One dying does not stop the
    others — that independence is exactly why `failed` goes to both Discord and
    mail.
    """
    log = get_logger()
    targets = [only] if only else cfg.routing.get(str(note.event), [])
    targets = [t for t in targets if t in channels.ALL]

    # If **none** of the routed channels are configured, send to whatever is.
    #
    # The default routing (done = smtp) assumes both channels exist. For a
    # Discord-only setup that makes done and custom dead paths where
    # notifications vanish silently. A notifier swallowing notifications without
    # a word is the worst failure available here, so reroute and log it.
    if not only and targets and not any(cfg.configured(t) for t in targets):
        fallback = cfg.active_channels()
        if fallback:
            log.info(
                "no configured target for %s (routed to %s) — sending to %s instead",
                note.event, ", ".join(targets), ", ".join(fallback),
            )
            targets = fallback

    if not targets:
        log.info("no routing target for %s", note.event)
        return []

    if not ignore_suppression:
        window = int(cfg.triggers.get("cooldown_sec", 60))
        if not state.cooled_down(note.session_id, str(note.event), window):
            log.info("suppressed by cooldown: %s (%ss)", note.event, window)
            return [Result(t, False, "cooldown") for t in targets]

    results: list[Result] = []
    for name in targets:
        results.append(_deliver(cfg, name, note, ignore_suppression=ignore_suppression))
    return results


def _deliver(
    cfg: Config, name: str, note: Notification, *, ignore_suppression: bool
) -> Result:
    log = get_logger()
    channel = channels.get(name)
    channel_cfg = cfg.channel(name)

    if not cfg.configured(name):
        log.info("%s: not configured, skipping", name)
        return Result(name, False, "not configured")

    if not ignore_suppression and name == "smtp":
        from mailo.channels.smtp import DEFAULT_DAILY_LIMIT

        limit = int(channel_cfg.get("daily_limit", DEFAULT_DAILY_LIMIT))
        if not state.quota_ok(name, limit):
            # Going over locks the user's real mail account, not mailo.
            log.warning("%s: daily cap of %d reached — not sending", name, limit)
            return Result(name, False, f"daily cap of {limit} reached")

    last: ChannelError | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            channel.send(channel_cfg, note.event, note.title, note.body, note.meta)
            log.info("%s: sent (%s)", name, note.event)
            return Result(name, True)
        except PermanentError as exc:
            log.error("%s: %s", name, exc.message)
            if exc.remedy:
                log.error("%s: fix — %s", name, exc.remedy.replace("\n", " "))
            return Result(name, False, f"failed: {exc.message}")
        except TransientError as exc:
            last = exc
            log.warning("%s: %s (attempt %d/%d)", name, exc.message, attempt, MAX_ATTEMPTS)
            if attempt < MAX_ATTEMPTS:
                time.sleep(exc.retry_after if exc.retry_after is not None else BACKOFF_SEC)

    message = last.message if last else "unknown error"
    log.error("%s: still failing after retry — %s", name, message)
    return Result(name, False, f"failed: {message}")


def verify(cfg: Config, name: str) -> str:
    """Check a channel's configuration — sends nothing."""
    return channels.get(name).verify(cfg.channel(name))


def describe(results: list[Result]) -> str:
    """A one-line summary for a human."""
    if not results:
        return "nothing to send"
    parts = []
    for r in results:
        mark = "sent" if r.sent else (r.detail or "failed")
        parts.append(f"{r.channel}={mark}")
    return ", ".join(parts)


def any_sent(results: list[Result]) -> bool:
    return any(r.sent for r in results)


__all__ = [
    "Notification",
    "Result",
    "any_sent",
    "build_meta",
    "describe",
    "dispatch",
    "verify",
]
