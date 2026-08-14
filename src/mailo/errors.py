"""Exception hierarchy.

One rule governs everything here: **the hook entry point is the only place that
swallows exceptions** (DESIGN.md §5.1). Everywhere below it, errors propagate.

Errors destined for a human carry a `remedy`. An error that only says what broke
is worth less than half of one that also says how to fix it.
"""

from __future__ import annotations


class MailoError(Exception):
    """An error safe to show the user verbatim."""

    def __init__(self, message: str, remedy: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.remedy = remedy.strip()


class ConfigError(MailoError):
    """Something wrong with the config file, a key, or a value."""


class ChannelError(MailoError):
    """Base class for delivery failures."""

    channel: str = "?"


class PermanentError(ChannelError):
    """Retrying is pointless — the configuration has to change.

    Bad credentials, a deleted webhook, an unsupported protocol. Give up
    immediately and log the `remedy`.
    """


class TransientError(ChannelError):
    """Worth retrying — connection errors, timeouts, 429, 5xx."""

    def __init__(self, message: str, remedy: str = "", retry_after: float | None = None) -> None:
        super().__init__(message, remedy)
        self.retry_after = retry_after
