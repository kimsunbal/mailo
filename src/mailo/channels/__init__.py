"""Channel adapter registry.

The shared contract (DESIGN.md §7.1, docs/channels/README.md):

- The interface is `send(cfg, event, title, body, meta) -> None`; failures raise.
- Channels are attempted **independently**. One failing does not stop the others.
- Truncation is each adapter's own business; the common message keeps the full text.
- Exceptions split into `PermanentError` (retrying is pointless) and
  `TransientError` (retrying is worth it).
- How an event looks is the adapter's decision — a colour bar on Discord, an
  emoji in the mail subject.

The `smtp` adapter accepts `event` and `meta` and mostly ignores them. A uniform
signature is still the better trade: the registry stays trivial and callers never
have to special-case a channel.
"""

from __future__ import annotations

from typing import Any, Protocol

from mailo.channels import discord as _discord
from mailo.channels import smtp as _smtp
from mailo.events import Event


class Channel(Protocol):
    """The shape every channel adapter satisfies."""

    NAME: str

    def send(
        self,
        cfg: dict[str, Any],
        event: Event,
        title: str,
        body: str,
        meta: dict[str, str],
    ) -> None: ...

    def verify(self, cfg: dict[str, Any]) -> str:
        """Check the config really works and return a human-readable confirmation.

        **Sends nothing.** Discord only reads the webhook back; SMTP only logs in.
        This has to be callable *before* anything is saved (DESIGN.md §6.3.5).
        """
        ...


REGISTRY: dict[str, Any] = {
    _discord.NAME: _discord,
    _smtp.NAME: _smtp,
}

ALL: tuple[str, ...] = tuple(REGISTRY)


def get(name: str) -> Any:
    from mailo.errors import ConfigError

    try:
        return REGISTRY[name]
    except KeyError:
        raise ConfigError(
            f"unknown channel: {name}", f"available channels: {', '.join(ALL)}"
        ) from None
