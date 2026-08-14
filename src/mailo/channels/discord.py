"""Discord webhook channel — the one that carries immediacy.

Built on `urllib.request` alone. The webhook URL is a credential, so **it is never
logged verbatim**.

Every limit here counts **characters, not bytes**, so non-ASCII text costs the
same as ASCII.
"""

from __future__ import annotations

import contextlib
import json
import re
import urllib.error
import urllib.request
from typing import Any, Final

from mailo.errors import PermanentError, TransientError
from mailo.events import Event

NAME: Final = "discord"

TIMEOUT: Final = 10
MAX_DESCRIPTION: Final = 4096
MAX_FIELD_VALUE: Final = 1024
MAX_TITLE: Final = 256

_WEBHOOK_RE: Final = re.compile(
    r"^https://(?:\w+\.)?discord(?:app)?\.com/api/webhooks/(\d+)/([\w-]+)$"
)

_REMEDY_BAD_URL: Final = (
    "The webhook was deleted or the URL is wrong.\n"
    "Re-issue it under Channel Settings -> Integrations -> Webhooks, then run\n"
    "  mailo config set discord.webhook_url"
)


def mask(url: str) -> str:
    """A form safe to print or log — the token is removed."""
    m = _WEBHOOK_RE.match(url or "")
    return f".../webhooks/{m.group(1)}/***" if m else "(webhook URL)"


def _url(cfg: dict[str, Any]) -> str:
    url = str(cfg.get("webhook_url") or "").strip()
    if not url:
        raise PermanentError(
            "no Discord webhook URL configured",
            "mailo config set discord.webhook_url",
        )
    return url


def _clip(text: str, limit: int) -> str:
    """Character-based truncation that does not hide the fact it truncated."""
    return text if len(text) <= limit else text[: limit - 1] + "…"


def build_payload(event: Event, title: str, body: str, meta: dict[str, str]) -> dict[str, Any]:
    """A payload with a single embed.

    The colour is `Event.color`, a hex `int`, passed straight through —
    `json.dumps` renders it as decimal. Nothing is converted by hand.
    """
    fields = [
        {"name": key, "value": _clip(str(value), MAX_FIELD_VALUE), "inline": True}
        for key, value in meta.items()
        if value
    ]
    embed: dict[str, Any] = {
        "title": _clip(f"{event.emoji} {title}", MAX_TITLE),
        "color": event.color,
    }
    if body:
        embed["description"] = _clip(body, MAX_DESCRIPTION)
    if fields:
        embed["fields"] = fields[:25]
    return {"embeds": [embed]}


def send(
    cfg: dict[str, Any],
    event: Event,
    title: str,
    body: str,
    meta: dict[str, str],
) -> None:
    _post(_url(cfg), build_payload(event, title, body, meta))


def _post(url: str, payload: dict[str, Any]) -> None:
    # `?wait=true` makes Discord answer 200 with the created message instead of a
    # bare 204. Without it we only learn the request was accepted, never that the
    # message reached the channel — and delivery is the entire job here.
    request = urllib.request.Request(
        f"{url}?wait=true",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": _agent()},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        raise _classify(exc) from exc
    except urllib.error.URLError as exc:
        raise TransientError(f"cannot reach Discord: {exc.reason}") from exc
    except TimeoutError as exc:
        raise TransientError("Discord request timed out") from exc


def _classify(exc: urllib.error.HTTPError) -> Exception:
    """Split HTTP failures into retryable and not.

    Retrying 401/403/404 piles up invalid requests and contributes to the
    **per-IP ban** (10,000 in 10 minutes). A retry loop against a deleted webhook
    can produce thousands per minute.
    """
    if exc.code in (401, 403, 404):
        return PermanentError(f"Discord rejected the request: {exc.code} {exc.reason}",
                              _REMEDY_BAD_URL)

    if exc.code == 429:
        wait = 5.0
        with contextlib.suppress(ValueError, AttributeError):
            wait = float(json.loads(exc.read() or b"{}").get("retry_after", wait))
        # Honour what the server asked for, but cap it — a `blocked` notification
        # two minutes late is the same as one never sent.
        if wait > 60:
            return PermanentError(
                f"Discord rate limit of {wait:.0f}s is not worth waiting out",
                "Send less often, or raise triggers.cooldown_sec.",
            )
        return TransientError("Discord rate limit (429)", retry_after=wait)

    if exc.code >= 500:
        return TransientError(f"Discord server error: {exc.code}")

    return PermanentError(f"Discord rejected the request: {exc.code} {exc.reason}")


def verify(cfg: dict[str, Any]) -> str:
    """**Read** the webhook back — nothing is posted to the channel.

    `GET /webhooks/{id}/{token}` needs only the token and creates no message, so
    it can run before the config is saved. Echoing the webhook's name back tells
    the user immediately if they pasted the wrong one.
    """
    url = _url(cfg)
    request = urllib.request.Request(url, headers={"User-Agent": _agent()}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            data = json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raise _classify(exc) from exc
    except urllib.error.URLError as exc:
        raise TransientError(f"cannot reach Discord: {exc.reason}") from exc

    name = data.get("name") or "unnamed"
    channel_id = data.get("channel_id")
    suffix = f" (channel {channel_id})" if channel_id else ""
    return f'webhook "{name}"{suffix}'


def _agent() -> str:
    from mailo import __version__

    return f"mailo/{__version__} (+https://github.com/1935138/mailo)"
