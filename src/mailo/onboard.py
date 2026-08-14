"""Onboarding — what `mailo init` does.

Three steps, in order (DESIGN.md §6.3).

1. **Look before asking.** Search for an existing configuration (the old
   `mailer.py` config, environment variables). Finding nothing costs nothing, so
   this is pure upside.
2. **One paste, no required order.** A question-and-answer flow assumes the user
   can follow *mailo's* order — but when it asks for the webhook URL they are on
   the Gmail tab. Over SSH every round trip is latency, too. So take whatever
   they collected in one lump and classify it by shape.
3. **Verify before saving.** The moment a wrong value settles into the file the
   user has to open an editor, and that is where onboarding fails.

There is no automatic issuance path. Discord OAuth2 and Gmail XOAUTH2 both need a
client secret shipped inside a public package, and RFC 6186 SRV autodiscovery
needs SRV lookups the standard library does not have. So the goal is not "remove
the paste" but **"make one paste impossible to get wrong, and remove even that
from the second machine onwards."**
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Final

from mailo.channels import smtp as smtp_channel
from mailo.schema import SCHEMA, coerce

# ── paste parsing ───────────────────────────────────────────────────────────

_WEBHOOK_RE: Final = re.compile(
    r"https://(?:\w+\.)?discord(?:app)?\.com/api/webhooks/\d+/[\w-]+"
)
_CHANNEL_URL_RE: Final = re.compile(r"https://(?:\w+\.)?discord(?:app)?\.com/channels/\S+")
_EMAIL_RE: Final = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_HOST_RE: Final = re.compile(r"\b(?:smtp|mail)[\w.-]*\.[a-z]{2,}\b", re.IGNORECASE)
_PORT_RE: Final = re.compile(r"\b(465|587|25|2525)\b")
#: A Gmail app password: 16 lowercase letters, usually shown in four groups of four.
_APP_PASSWORD_RE: Final = re.compile(r"\b[a-z]{4}[ \t]*[a-z]{4}[ \t]*[a-z]{4}[ \t]*[a-z]{4}\b")
#: `KEY=VALUE` / `key: value` — lets an entire old config file be pasted as is.
_ASSIGN_RE: Final = re.compile(r"^\s*([A-Za-z_][\w.]*)\s*[=:]\s*(.+?)\s*$")

#: Flat keys from the old `mailer.py` config, mapped to mailo short keys.
LEGACY_KEYS: Final[dict[str, str]] = {
    "username": "smtp.username",
    "app_password": "smtp.password",
    "password": "smtp.password",
    "default_to": "smtp.to",
    "to": "smtp.to",
    "smtp_host": "smtp.host",
    "smtp_port": "smtp.port",
    "subject_prefix": "machine",
    "machine": "machine",
    "webhook_url": "discord.webhook_url",
}


class Parsed(dict):
    """Recognised `short key -> value`, plus what could not be identified."""

    leftovers: list[str]
    warnings: list[str]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.leftovers = []
        self.warnings = []


def parse_blob(text: str) -> Parsed:
    """Extract configuration values from a pasted lump.

    Every value is **distinguishable by shape alone.** A webhook URL, an email
    address, sixteen lowercase letters, and an `smtp.*` hostname cannot be
    confused with one another, which is why no ordering has to be imposed.

    Matches are removed from the text as they are found — emails have to go
    before the app-password pattern, or it would bite into a local part.
    """
    found = Parsed()
    rest = text

    # 0. Explicit `KEY=VALUE` lines win. This is what lets a whole legacy config
    #    file be pasted straight in.
    consumed: list[str] = []
    for line in rest.splitlines():
        m = _ASSIGN_RE.match(line)
        if not m:
            continue
        raw_key, raw_value = m.group(1).strip(), _unwrap(m.group(2))
        key = LEGACY_KEYS.get(raw_key.lower(), raw_key if raw_key in SCHEMA else "")
        if not key or not raw_value:
            continue
        found[key] = _clean(key, raw_value)
        consumed.append(line)
    for line in consumed:
        rest = rest.replace(line, " ")

    # 1. Discord webhook URL
    if "discord.webhook_url" not in found:
        m = _WEBHOOK_RE.search(rest)
        if m:
            found["discord.webhook_url"] = m.group(0)
            rest = rest.replace(m.group(0), " ")
        elif _CHANNEL_URL_RE.search(rest):
            found.warnings.append(
                "That is a channel URL, not a webhook URL.\n"
                "Get one from Channel Settings -> Integrations -> Webhooks -> New Webhook."
            )
            rest = _CHANNEL_URL_RE.sub(" ", rest)

    # 2. Email addresses — the first is the sender, a second becomes the recipient
    emails = _EMAIL_RE.findall(rest)
    for address in emails:
        rest = rest.replace(address, " ")
    if emails:
        found.setdefault("smtp.username", emails[0])
        found.setdefault("smtp.to", emails[1] if len(emails) > 1 else emails[0])

    # 3. Server and port (usually unnecessary — the preset derives them)
    if "smtp.host" not in found:
        m = _HOST_RE.search(rest)
        if m:
            found["smtp.host"] = m.group(0).lower()
            rest = rest.replace(m.group(0), " ")
    if "smtp.port" not in found:
        m = _PORT_RE.search(rest)
        if m:
            found["smtp.port"] = int(m.group(1))
            rest = rest.replace(m.group(0), " ")

    # 4. App password — only safe once emails and URLs are out of the way
    if "smtp.password" not in found:
        m = _APP_PASSWORD_RE.search(rest)
        if m:
            found["smtp.password"] = re.sub(r"\s+", "", m.group(0))
            rest = rest.replace(m.group(0), " ")

    apply_preset(found)
    found.leftovers = [w for w in rest.split() if len(w) > 3][:5]
    return found


def _unwrap(value: str) -> str:
    """Strip quotes and brackets, for values like `SUBJECT_PREFIX=[box]`."""
    value = value.strip().strip("\"'").strip()
    if value.startswith("[") and value.endswith("]") and "," not in value:
        value = value[1:-1].strip()
    return value


def _clean(key: str, value: str) -> Any:
    if key == "smtp.password":
        return re.sub(r"\s+", "", value)
    if key in SCHEMA and SCHEMA[key].kind == "int":
        try:
            return int(value)
        except ValueError:
            return value
    return value


def apply_preset(found: dict[str, Any]) -> None:
    """Derive the SMTP server from the email domain — five fields down to two."""
    address = found.get("smtp.username")
    if not address or "smtp.host" in found:
        return
    preset = smtp_channel.preset_for(str(address))
    if preset:
        host, port, security = preset
        found["smtp.host"] = host
        found.setdefault("smtp.port", port)
        found.setdefault("smtp.security", security)


def validate(found: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Run everything through the schema, returning what passed and why the rest did not."""
    from mailo.errors import ConfigError

    clean: dict[str, Any] = {}
    problems: list[str] = []
    for key, value in found.items():
        try:
            clean[key] = coerce(key, str(value)) if not isinstance(value, bool) else value
        except ConfigError as exc:
            problems.append(exc.message)
    return clean, problems


# ── finding an existing configuration ───────────────────────────────────────

LEGACY_PATHS: Final = (
    Path.home() / "tools" / "mailer" / "config",
    Path.home() / ".mailer" / "config",
)


def discover() -> tuple[dict[str, Any], str]:
    """Look for a configuration that already exists. Returns `(values, source)`.

    The old `mailer.py` flat `KEY=VALUE` config maps one-to-one onto mailo keys.
    When it turns up, the user only has to add a Discord webhook and they are done.
    """
    for path in LEGACY_PATHS:
        try:
            if path.is_file():
                found = parse_blob(path.read_text(encoding="utf-8"))
                if found:
                    return dict(found), str(path)
        except OSError:
            continue

    from_env: dict[str, Any] = {}
    for key, spec in SCHEMA.items():
        if len(spec.path) != 3:
            continue
        env_name = f"MAILO_{spec.path[1].upper()}_{spec.name.upper()}"
        if os.environ.get(env_name):
            from_env[key] = os.environ[env_name]
    if from_env:
        apply_preset(from_env)
        return from_env, "environment variables"

    return {}, ""
