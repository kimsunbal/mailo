"""The config key schema — **one table feeding three consumers** (DESIGN.md §6.3.3).

`mailo init`, `mailo config set`, and validation at load time all read from here.
Keep two copies of this and they will drift.

Keys are short. The real TOML path is `channels.smtp.username`, but the CLI takes
`smtp.username` — channel names never collide with the top-level keys (`machine`,
`routing`, `triggers`), so there is no ambiguity, and it ends up as terse as
`git config user.email`.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Final

from mailo.errors import ConfigError
from mailo.events import Event

CHANNELS: Final = ("discord", "smtp")

_EMAIL_RE: Final = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_WEBHOOK_RE: Final = re.compile(
    r"^https://(?:\w+\.)?discord(?:app)?\.com/api/webhooks/(\d+)/([\w-]+)$"
)


@dataclass(frozen=True, slots=True)
class Key:
    """The definition of a single config key."""

    path: tuple[str, ...]
    """Where it actually lives in the TOML."""

    kind: str
    """`str` | `int` | `bool` | `list` | `enum`"""

    help: str
    secret: bool = False
    choices: tuple[str, ...] = ()
    check: Callable[[Any], str] | None = field(default=None, compare=False)
    """Return a reason string if the value is wrong, an empty string if it is fine."""

    @property
    def section(self) -> str:
        """TOML section name; empty for a top-level key."""
        return ".".join(self.path[:-1])

    @property
    def name(self) -> str:
        return self.path[-1]


def _check_email(v: Any) -> str:
    return "" if _EMAIL_RE.match(str(v)) else "not an email address"


def _check_webhook(v: Any) -> str:
    url = str(v)
    if _WEBHOOK_RE.match(url):
        return ""
    if "discord.com/channels/" in url:
        return (
            "that is a channel URL, not a webhook URL. "
            "You need the one from Channel Settings -> Integrations -> Webhooks"
        )
    return "expected https://discord.com/api/webhooks/{id}/{token}"


def _check_port(v: Any) -> str:
    return "" if 1 <= int(v) <= 65535 else "must be between 1 and 65535"


def _check_nonneg(v: Any) -> str:
    return "" if int(v) >= 0 else "must be zero or greater"


def _check_channels(v: Any) -> str:
    unknown = [c for c in v if c not in CHANNELS]
    if unknown:
        return f"unknown channel: {', '.join(unknown)} (available: {', '.join(CHANNELS)})"
    return ""


SCHEMA: Final[dict[str, Key]] = {
    "machine": Key(
        ("machine",), "str", "identifier for this machine; defaults to the hostname"
    ),
    # ── SMTP ────────────────────────────────────────────────────────────
    "smtp.host": Key(("channels", "smtp", "host"), "str", "SMTP server address"),
    "smtp.port": Key(
        ("channels", "smtp", "port"), "int", "465 (implicit TLS) or 587 (STARTTLS)",
        check=_check_port,
    ),
    "smtp.security": Key(
        ("channels", "smtp", "security"), "enum",
        "tls = implicit TLS (465) | starttls = STARTTLS (587)",
        choices=("tls", "starttls"),
    ),
    "smtp.username": Key(
        ("channels", "smtp", "username"), "str",
        "the full email address, not the part before the @", check=_check_email,
    ),
    "smtp.password": Key(
        ("channels", "smtp", "password"), "str",
        "for Gmail this is an app password, not your account password", secret=True,
    ),
    "smtp.to": Key(
        ("channels", "smtp", "to"), "str", "recipient address", check=_check_email
    ),
    "smtp.daily_limit": Key(
        ("channels", "smtp", "daily_limit"), "int",
        "messages per day; 0 means unlimited", check=_check_nonneg,
    ),
    # ── Discord ─────────────────────────────────────────────────────────
    "discord.webhook_url": Key(
        ("channels", "discord", "webhook_url"), "str",
        "copied from Channel Settings -> Integrations -> Webhooks",
        secret=True, check=_check_webhook,
    ),
    # ── routing ─────────────────────────────────────────────────────────
    **{
        f"routing.{e.value}": Key(
            ("routing", e.value), "list",
            f"channels that receive the {e.value} event", check=_check_channels,
        )
        for e in Event
    },
    # ── triggers ────────────────────────────────────────────────────────
    "triggers.blocked_delay_sec": Key(
        ("triggers", "blocked_delay_sec"), "int",
        "how long the session must stay blocked before notifying", check=_check_nonneg,
    ),
    "triggers.cooldown_sec": Key(
        ("triggers", "cooldown_sec"), "int",
        "suppress repeats of the same (session, event) for this long", check=_check_nonneg,
    ),
    "triggers.include_message_text": Key(
        ("triggers", "include_message_text"), "bool",
        "put conversation text in the body; false by default because it leaves the machine",
    ),
    "triggers.stop_min_duration_sec": Key(
        ("triggers", "stop_min_duration_sec"), "int",
        "opt-in; with this key absent the Stop hook is not registered at all",
        check=_check_nonneg,
    ),
}

SECRET_KEYS: Final = frozenset(k for k, v in SCHEMA.items() if v.secret)


def lookup(key: str) -> Key:
    """Resolve a short key, rejecting unknown ones with a near match.

    `git config` accepts arbitrary keys; mailo does not. Accepting a typo here
    means **nobody finds out until a notification fails to send**, and silently
    doing nothing is the worst failure this tool has.
    """
    if key in SCHEMA:
        return SCHEMA[key]

    import difflib

    near = difflib.get_close_matches(key, SCHEMA, n=3, cutoff=0.6)
    remedy = f"did you mean: {', '.join(near)}" if near else "run `mailo config list`"
    raise ConfigError(f"unknown config key: {key}", remedy)


def coerce(key: str, raw: str) -> Any:
    """Convert CLI input to the schema type and validate it.

    Everything arriving from the command line is a string. Without this gate a
    value like `cooldown_sec = "60s"` settles into the config file and only
    explodes at the next send.
    """
    spec = lookup(key)
    text = raw.strip()

    value: Any
    match spec.kind:
        case "int":
            try:
                value = int(text)
            except ValueError:
                raise ConfigError(f"{key} must be an integer: {text!r}", spec.help) from None
        case "bool":
            low = text.lower()
            if low in {"true", "yes", "y", "1", "on"}:
                value = True
            elif low in {"false", "no", "n", "0", "off"}:
                value = False
            else:
                raise ConfigError(f"{key} must be true or false: {text!r}", spec.help)
        case "list":
            value = [p.strip() for p in text.split(",") if p.strip()]
        case "enum":
            if text not in spec.choices:
                raise ConfigError(
                    f"{key} must be one of {' | '.join(spec.choices)}: {text!r}", spec.help
                )
            value = text
        case _:
            value = text

    if spec.check:
        reason = spec.check(value)
        if reason:
            raise ConfigError(f"{key}: {reason}", spec.help)
    return value


def mask(key: str, value: Any) -> str:
    """Show just enough of a secret for the user to recognise it.

    Hide all of it and they cannot confirm what they typed; show all of it and it
    leaks over their shoulder.
    """
    if key not in SECRET_KEYS or not value:
        return _render(value)

    text = str(value)
    if key == "discord.webhook_url":
        m = _WEBHOOK_RE.match(text)
        return f".../webhooks/{m.group(1)}/***" if m else "***"
    return "*" * min(len(text), 16) + f" ({len(text)} chars)"


def _render(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)
