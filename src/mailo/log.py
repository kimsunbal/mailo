"""Logging — `$XDG_STATE_HOME/mailo/mailo.log`.

The hook path has no screen. This file is the only way to debug a notifier that
is failing quietly.

**Credentials never land here.** The Discord webhook URL is itself a credential,
which makes the reflex of "log the request URL" a leak. Channel adapters hand
over masked strings, and this module sweeps once more on the way out.
"""

from __future__ import annotations

import logging
import os
import re
from logging.handlers import RotatingFileHandler
from typing import Final

from mailo.config import state_dir

_WEBHOOK_RE: Final = re.compile(r"(/api/webhooks/\d+)/[\w-]+")
_logger: logging.Logger | None = None


class _Redactor(logging.Filter):
    """Last line of defence: strip webhook tokens that got in by any route."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _WEBHOOK_RE.sub(r"\1/***", record.msg)
        return True


def get() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger

    logger = logging.getLogger("mailo")
    logger.setLevel(logging.DEBUG if os.environ.get("MAILO_DEBUG") else logging.INFO)
    logger.propagate = False

    try:
        directory = state_dir()
        directory.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = RotatingFileHandler(
            directory / "mailo.log", maxBytes=512_000, backupCount=2, encoding="utf-8"
        )
    except OSError:  # a missing log must not stop delivery
        handler = logging.NullHandler()

    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
    handler.addFilter(_Redactor())
    logger.addHandler(handler)

    _logger = logger
    return logger
