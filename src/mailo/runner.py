"""`mailo run` — wrap a command and notify when it ends.

Used as `mailo run -- ./run-train.sh`. Unlike the hook path, **this one knows for
certain that the command ended**, and knows the exit code, the duration, and the
last output exactly.

Output is streamed through while only the final few lines are retained. There is
no reason to hold the whole thing in memory just to attach a tail.

**Limitation**: the child's stdout is a pipe, so this does not suit interactive
programs that need a TTY. It is for wrapping long batch jobs.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
import time
from collections import deque
from collections.abc import Sequence
from pathlib import Path

from mailo import notify
from mailo.config import Config
from mailo.events import Event

TAIL_LINES = 5


def run(cfg: Config, command: Sequence[str], *, name: str | None = None) -> int:
    """Run the command, notify, and return the child's exit code unchanged."""
    label = name or Path(command[0]).name
    started = time.monotonic()
    tail: deque[str] = deque(maxlen=TAIL_LINES)

    try:
        code = _stream(command, tail)
    except FileNotFoundError:
        from mailo.errors import MailoError

        raise MailoError(
            f"cannot execute: {command[0]}",
            f"Check the path and the executable bit: {shlex.join(command)}",
        ) from None
    except KeyboardInterrupt:
        code = 130

    elapsed = time.monotonic() - started
    event = Event.DONE if code == 0 else Event.FAILED
    suffix = "done" if code == 0 else f"failed (exit {code})"

    note = notify.Notification(
        event=event,
        title=f"[{cfg.machine}] {label} — {suffix}",
        body=_tail_block(tail),
        meta=notify.build_meta(
            cfg, cwd=str(Path.cwd()), elapsed=elapsed, exit_code=code,
            extra={"command": shlex.join(command)[:200]},
        ),
        session_id=f"run:{label}",
    )
    # The user invoked this command directly; do not let cooldown swallow it.
    notify.dispatch(cfg, note, ignore_suppression=True)
    return code


def _stream(command: Sequence[str], tail: deque[str]) -> int:
    """Pass the child's output through while keeping the last lines."""
    with subprocess.Popen(
        list(command),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        errors="replace",
    ) as proc:
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            stripped = line.rstrip("\n")
            if stripped:
                tail.append(stripped)
        return proc.wait()


def _tail_block(tail: deque[str]) -> str:
    if not tail:
        return ""
    lines = [f"--- last {len(tail)} lines ---", *tail]
    return "\n".join(lines)
