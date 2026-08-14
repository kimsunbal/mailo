"""The config file — reading, validating, and writing in place.

`~/.config/mailo/config.toml`, overridable with `$MAILO_CONFIG`.

**Mode 600 is enforced.** The SMTP password and the Discord webhook URL both live
here, and the webhook URL *is* a credential — anyone holding it can post to that
channel.
"""

from __future__ import annotations

import os
import socket
import stat
import tomllib
from pathlib import Path
from typing import Any, Final

from mailo import tomlwrite
from mailo.errors import ConfigError
from mailo.events import Event
from mailo.schema import SCHEMA, coerce, lookup

DEFAULT_ROUTING: Final[dict[str, list[str]]] = {
    Event.BLOCKED: ["discord"],
    Event.FAILED: ["discord", "smtp"],
    Event.DONE: ["smtp"],
    Event.CUSTOM: ["smtp"],
}

DEFAULT_TRIGGERS: Final[dict[str, Any]] = {
    # 0 = send immediately. Hook input carries no "no longer blocked" signal, so
    # v1 does not delay (DESIGN.md §10 Q3). A non-zero value waits for the
    # session to be observed as still blocked a second time.
    "blocked_delay_sec": 0,
    "cooldown_sec": 60,
    "include_message_text": False,
}

TEMPLATE: Final = """\
# mailo config. Keep this at mode 600 — it holds credentials.
# Full key list: mailo config list

# Identifier for this machine, prefixed to every notification title.
# Omit it and the hostname is used, so this file can be copied to another machine as is.

[routing]
blocked = ["discord"]            # immediacy is the whole point -> phone push
failed  = ["discord", "smtp"]    # two independent paths; one can die
done    = ["smtp"]               # a record is enough
custom  = ["smtp"]

[triggers]
cooldown_sec = 60                # suppress repeats of the same (session, event)
# blocked_delay_sec = 90         # opt-in: notify only if still blocked this long
include_message_text = false     # turning this on sends conversation text off-machine
# stop_min_duration_sec = 300    # opt-in; absent means the Stop hook is not registered

[channels.discord]
# webhook_url = ""               # never logged — the URL itself is a credential

[channels.smtp]
# host = "smtp.gmail.com"
# port = 465
# security = "tls"               # "tls" = implicit TLS (465) | "starttls" = STARTTLS (587)
# username = ""                  # full address, not the part before the @
# password = ""                  # or $MAILO_SMTP_PASSWORD
# to = ""
# daily_limit = 200              # 0 means unlimited
"""


def config_path() -> Path:
    """`$MAILO_CONFIG` > `$XDG_CONFIG_HOME` > `~/.config`."""
    override = os.environ.get("MAILO_CONFIG")
    if override:
        return Path(override).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base).expanduser() / "mailo" / "config.toml"


def state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"
    return Path(base).expanduser() / "mailo"


# ── reading ─────────────────────────────────────────────────────────────────


class Config:
    """A validated configuration, treated as read-only."""

    __slots__ = ("data", "path")

    def __init__(self, data: dict[str, Any], path: Path) -> None:
        self.data = data
        self.path = path

    # convenience accessors --------------------------------------------------

    @property
    def machine(self) -> str:
        """Machine identifier, falling back to the hostname.

        That fallback is what lets **one config file be copied to N machines**
        while notifications still say where they came from (DESIGN.md §6.3.7).
        """
        return str(self.data.get("machine") or socket.gethostname())

    @property
    def routing(self) -> dict[str, list[str]]:
        merged = dict(DEFAULT_ROUTING)
        merged.update(self.data.get("routing") or {})
        return merged

    @property
    def triggers(self) -> dict[str, Any]:
        merged = dict(DEFAULT_TRIGGERS)
        merged.update(self.data.get("triggers") or {})
        return merged

    def channel(self, name: str) -> dict[str, Any]:
        """Channel config with environment overrides applied.

        `$MAILO_<CHANNEL>_<KEY>` — for example `$MAILO_SMTP_PASSWORD` or
        `$MAILO_DISCORD_WEBHOOK_URL` — beats the file. This is the path for
        containers and CI, where planting a config file is awkward.
        """
        cfg = dict((self.data.get("channels") or {}).get(name) or {})
        prefix = f"MAILO_{name.upper()}_"
        for env_key, env_value in os.environ.items():
            if env_key.startswith(prefix) and env_value:
                cfg[env_key[len(prefix) :].lower()] = env_value
        return cfg

    def configured(self, name: str) -> bool:
        """Whether this channel can actually be used."""
        cfg = self.channel(name)
        if name == "discord":
            return bool(cfg.get("webhook_url"))
        if name == "smtp":
            return bool(cfg.get("host") and cfg.get("username") and cfg.get("to"))
        return False

    def active_channels(self) -> list[str]:
        return [c for c in ("discord", "smtp") if self.configured(c)]

    def get(self, key: str) -> Any:
        """Read one value by short key, or `None`."""
        node: Any = self.data
        for part in lookup(key).path:
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        return node


def load(*, require: bool = True) -> Config:
    """Read and validate the config."""
    path = config_path()
    if not path.exists():
        if require:
            raise ConfigError(
                f"no config file at {path}",
                "Create one with `mailo init`. If another machine already has one, "
                "pipe `mailo config export` there into `mailo init --from -`.",
            )
        return Config({}, path)

    _check_permissions(path)

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"cannot read config: {path}", f"TOML syntax error — {exc}") from exc

    _validate(data)
    return Config(data, path)


def _check_permissions(path: Path) -> None:
    """Refuse to read a file other users can read.

    A warning would be ignored. This file holds credentials, so it is a hard stop.
    """
    if os.name == "nt":  # Windows does not use the POSIX permission model
        return
    mode = path.stat().st_mode
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise ConfigError(
            f"config file permissions are too open: {path} ({stat.filemode(mode)})",
            f"chmod 600 {path}",
        )


def _validate(data: dict[str, Any]) -> None:
    """Only schema keys, only schema types."""
    for key, spec in SCHEMA.items():
        node: Any = data
        for part in spec.path:
            if not isinstance(node, dict) or part not in node:
                node = None
                break
            node = node[part]
        if node is None:
            continue
        if spec.kind == "int" and not isinstance(node, int):
            raise ConfigError(f"{key} must be an integer: {node!r}", spec.help)
        if spec.kind == "bool" and not isinstance(node, bool):
            raise ConfigError(f"{key} must be true or false: {node!r}", spec.help)
        if spec.kind == "list" and not isinstance(node, list):
            raise ConfigError(f"{key} must be an array: {node!r}", spec.help)
        if spec.check:
            reason = spec.check(node)
            if reason:
                raise ConfigError(f"{key}: {reason}", spec.help)


# ── writing ─────────────────────────────────────────────────────────────────


def ensure_file() -> Path:
    """Create the annotated template if no config exists yet."""
    path = config_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_atomic(path, TEMPLATE)
    return path


def set_key(key: str, value: Any) -> Path:
    """Write one key via in-place editing.

    Afterwards the result is **parsed again with `tomllib`**. Line editing can go
    wrong on quoting and escapes, so the round trip is the safety net; if it
    fails, the original file is left untouched.
    """
    spec = lookup(key)
    path = ensure_file()
    original = path.read_text(encoding="utf-8")
    updated = tomlwrite.set_value(original, spec.section, spec.name, value)

    try:
        tomllib.loads(updated)
    except tomllib.TOMLDecodeError as exc:  # pragma: no cover - defensive
        raise ConfigError(
            f"writing {key} would corrupt the config; the original was kept",
            f"TOML error: {exc}. Fix it by hand with `mailo config edit`.",
        ) from exc

    _write_atomic(path, updated)
    return path


def unset_key(key: str) -> bool:
    spec = lookup(key)
    path = config_path()
    if not path.exists():
        return False
    original = path.read_text(encoding="utf-8")
    updated, removed = tomlwrite.unset(original, spec.section, spec.name)
    if removed:
        _write_atomic(path, updated)
    return removed


def apply_many(pairs: dict[str, Any]) -> Path:
    """Write several keys — the path `init` takes.

    `init` amounts to calling `config set` repeatedly; it shares the schema and
    the validation rather than duplicating them.
    """
    ensure_file()
    path = config_path()
    for key, value in pairs.items():
        set_key(key, value)
    return path


def adapt_routing(cfg: Config) -> dict[str, list[str]]:
    """Routing entries that need to change to match the configured channels.

    The default routing assumes both channels exist (`done = ["smtp"]`). For
    someone who only set up Discord, `done` and `custom` have nowhere to go, so
    `init` writes routing that matches reality. The runtime fallback in
    `notify.dispatch` would catch it anyway, but **a config file should not lie.**
    """
    active = cfg.active_channels()
    if not active:
        return {}
    changed: dict[str, list[str]] = {}
    for event, targets in cfg.routing.items():
        kept = [t for t in targets if t in active] or active
        if kept != list(targets):
            changed[f"routing.{event}"] = kept
    return changed


def _write_atomic(path: Path, text: str) -> None:
    """Write to a temp file, **narrow the permissions first**, then swap it in.

    The order matters: writing the contents and chmod-ing afterwards leaves a
    window where another process can read it.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp{os.getpid()}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    if os.name != "nt":
        os.chmod(path, 0o600)


# ── moving between machines ─────────────────────────────────────────────────

EXPORT_PREFIX: Final = "MAILO1:"


def export(*, secrets: bool = True) -> str:
    """The whole config as a single line, for pasting on another machine.

    **This is not encryption.** base64 is an encoding, not protection, so the
    string must be handled exactly like the plaintext credentials it contains.
    The caller prints that warning alongside it.
    """
    import base64
    import json
    import zlib

    from mailo.schema import SECRET_KEYS

    cfg = load()
    payload: dict[str, Any] = {}
    for key in SCHEMA:
        if not secrets and key in SECRET_KEYS:
            continue
        value = cfg.get(key)
        if value is not None:
            payload[key] = value
    # `machine` is deliberately dropped: it must differ per machine, and leaving
    # it out lets the hostname fill it in.
    payload.pop("machine", None)

    blob = zlib.compress(json.dumps(payload, ensure_ascii=False).encode("utf-8"), 9)
    return EXPORT_PREFIX + base64.urlsafe_b64encode(blob).decode("ascii")


def import_line(line: str) -> dict[str, Any]:
    """Reverse `export`, discarding anything not in the schema."""
    import base64
    import json
    import zlib

    text = line.strip()
    if not text.startswith(EXPORT_PREFIX):
        raise ConfigError(
            "not a transfer string",
            f"It must start with {EXPORT_PREFIX}. "
            "Generate one with `mailo config export` on the other machine.",
        )
    try:
        blob = zlib.decompress(base64.urlsafe_b64decode(text[len(EXPORT_PREFIX) :]))
        payload = json.loads(blob.decode("utf-8"))
    except Exception as exc:
        raise ConfigError(
            "the transfer string is corrupt", "Check that it arrived on one line, unbroken."
        ) from exc

    if not isinstance(payload, dict):
        raise ConfigError("the transfer string does not contain a config", "")

    result: dict[str, Any] = {}
    for key, value in payload.items():
        if key not in SCHEMA:
            continue
        result[key] = coerce(key, ",".join(map(str, value))) if isinstance(value, list) else value
    return result
