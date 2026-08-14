"""Terminal output and input.

Colour is used **only on a TTY**. `NO_COLOR` (https://no-color.org) and
`TERM=dumb` are honoured, and nothing is emitted when the stream is a pipe —
`mailo config get` output is meant to be another program's input.

Symbols follow the same rule: if the terminal encoding cannot carry them, they
degrade to ASCII.
"""

from __future__ import annotations

import getpass
import os
import sys
from collections.abc import Iterable, Sequence
from typing import IO, Final

# ── colour ──────────────────────────────────────────────────────────────────


def _supports_color(stream: IO[str]) -> bool:
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return hasattr(stream, "isatty") and stream.isatty()


_COLOR: Final = _supports_color(sys.stdout)


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


def bold(t: str) -> str:
    return _c("1", t)


def dim(t: str) -> str:
    return _c("2", t)


def red(t: str) -> str:
    return _c("31", t)


def green(t: str) -> str:
    return _c("32", t)


def yellow(t: str) -> str:
    return _c("33", t)


def blue(t: str) -> str:
    return _c("36", t)


# ── symbols ─────────────────────────────────────────────────────────────────


def _unicode_ok() -> bool:
    enc = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        "✓→·".encode(enc)
    except (UnicodeEncodeError, LookupError):
        return False
    return True


_UNI: Final = _unicode_ok()

TICK: Final = "✓" if _UNI else "+"
CROSS: Final = "✗" if _UNI else "x"
ARROW: Final = "→" if _UNI else "->"
DOT: Final = "·" if _UNI else "-"


# ── output ──────────────────────────────────────────────────────────────────


def out(text: str = "") -> None:
    print(text)


def ok(text: str) -> None:
    print(f"{green(TICK)} {text}")


def fail(text: str) -> None:
    print(f"{red(CROSS)} {text}", file=sys.stderr)


def warn(text: str) -> None:
    print(f"{yellow('!')} {text}", file=sys.stderr)


def info(text: str) -> None:
    print(f"{blue(ARROW)} {text}")


def hint(text: str) -> None:
    """How to fix it. Multi-line hints are indented as a block."""
    for line in text.splitlines():
        print(dim(f"  {line}"), file=sys.stderr)


def rule(title: str = "") -> None:
    width = min(_term_width(), 72)
    if not title:
        print(dim("─" * width if _UNI else "-" * width))
        return
    bar = "─" if _UNI else "-"
    pad = max(0, width - len(title) - 3)
    print(dim(f"{bar}{bar} ") + bold(title) + dim(" " + bar * pad))


def _term_width() -> int:
    try:
        return os.get_terminal_size().columns
    except OSError:
        return 80


def kv(rows: Sequence[tuple[str, str]], indent: int = 2) -> None:
    """Print aligned key/value rows. An empty sequence prints nothing."""
    if not rows:
        return
    width = max(len(k) for k, _ in rows)
    pad = " " * indent
    for key, value in rows:
        print(f"{pad}{dim(key.ljust(width))}  {value}")


def bullets(items: Iterable[str], indent: int = 2) -> None:
    pad = " " * indent
    for item in items:
        print(f"{pad}{dim(DOT)} {item}")


# ── input ───────────────────────────────────────────────────────────────────


def ask(prompt: str, default: str = "") -> str:
    """Read one line, showing the default in brackets when there is one."""
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        return default
    return answer or default


def confirm(prompt: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    try:
        answer = input(f"{prompt} {suffix} ").strip().lower()
    except EOFError:
        return default
    if not answer:
        return default
    return answer in {"y", "yes"}


def secret(prompt: str) -> str:
    """Read a secret without echoing it.

    Nothing lands in shell history or on a screen recording. This is the only
    interactive path that accepts a credential (DESIGN.md §6.3.6).
    """
    try:
        return getpass.getpass(f"{prompt}: ").strip()
    except EOFError:
        return ""


def read_stdin() -> str:
    """Everything piped or redirected in."""
    return sys.stdin.read()


def paste(prompt: str) -> str:
    """Read a multi-line paste, terminated by EOF."""
    print(prompt)
    print(dim(f"  (paste, then press {'Ctrl-Z, Enter' if os.name == 'nt' else 'Ctrl-D'})"))
    print()
    try:
        return sys.stdin.read()
    except (EOFError, KeyboardInterrupt):
        return ""
