"""In-place TOML editing.

**The standard library has no TOML writer.** `tomllib` only parses. So
`config set` cannot be "load into objects, serialise back" — it has to be
**line-level editing in place**.

Re-serialising the whole file would wipe out the comments and the ordering on the
very first `config set`. Comments mattering in a file humans edit by hand was the
reason for choosing TOML in the first place (DESIGN.md §6.1); having the tool
destroy them would be incoherent.

The scope is only what mailo's schema uses: top-level keys, `[a]` and `[a.b]`
sections, and string / integer / boolean / string-array values. Inline tables,
array-of-tables (`[[x]]`), and multi-line strings are neither written nor touched.
"""

from __future__ import annotations

import re
from typing import Any, Final

_SECTION_RE: Final = re.compile(r"^\s*\[([^\[\]]+)\]\s*(?:#.*)?$")


def dumps_value(value: Any) -> str:
    """Render a Python value as a TOML literal."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(dumps_value(v) for v in value) + "]"
    return _quote(str(value))


def _quote(text: str) -> str:
    escaped = (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
        .replace("\r", "\\r")
    )
    return f'"{escaped}"'


def split_comment(rest: str) -> tuple[str, str]:
    """Split `value  # comment`. A `#` inside a string literal is not a comment."""
    in_string = False
    quote = ""
    escaped = False
    for i, ch in enumerate(rest):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                in_string = False
        elif ch in "\"'":
            in_string = True
            quote = ch
        elif ch == "#":
            return rest[:i].rstrip(), rest[i:]
    return rest.rstrip(), ""


def _sections(lines: list[str]) -> list[tuple[str, int, int]]:
    """`[(section, body_start, body_end_exclusive)]`. The top level has an empty name."""
    bounds: list[tuple[str, int, int]] = []
    current = ""
    start = 0
    for i, line in enumerate(lines):
        m = _SECTION_RE.match(line)
        if m:
            bounds.append((current, start, i))
            current = m.group(1).strip()
            start = i + 1
    bounds.append((current, start, len(lines)))
    return bounds


def _key_re(name: str) -> re.Pattern[str]:
    return re.compile(rf"^(\s*)(#\s*)?({re.escape(name)}|\"{re.escape(name)}\")(\s*=\s*)(.*)$")


def set_value(text: str, section: str, name: str, value: Any) -> str:
    """Return `text` with `section`'s `name` set to `value`.

    In priority order:

    1. An active line: replace only the value, keeping any trailing comment.
    2. A commented-out line: **uncomment it where it stands.** An opt-in key like
       `# stop_min_duration_sec = 300` settles back into its documented place.
    3. Section present but key absent: append to the end of that section.
    4. No such section: append the section and the key to the file.
    """
    lines = text.splitlines()
    literal = dumps_value(value)
    pattern = _key_re(name)

    commented: tuple[int, re.Match[str]] | None = None
    tail: int | None = None
    found_section = False

    for sec_name, start, end in _sections(lines):
        if sec_name != section:
            continue
        found_section = True
        tail = _insert_point(lines, start, end)
        for i in range(start, end):
            m = pattern.match(lines[i])
            if not m:
                continue
            if m.group(2):  # commented out
                if commented is None:
                    commented = (i, m)
                continue
            _, trailing = split_comment(m.group(5))
            lines[i] = f"{m.group(1)}{name}{m.group(4)}{literal}"
            if trailing:
                lines[i] += f"  {trailing}"
            return _join(lines)

    if commented is not None:
        i, m = commented
        _, trailing = split_comment(m.group(5))
        lines[i] = f"{m.group(1)}{name} = {literal}"
        if trailing:
            lines[i] += f"  {trailing}"
        return _join(lines)

    if found_section and tail is not None:
        lines.insert(tail, f"{name} = {literal}")
        return _join(lines)

    if lines and lines[-1].strip():
        lines.append("")
    lines.append(f"[{section}]")
    lines.append(f"{name} = {literal}")
    return _join(lines)


def unset(text: str, section: str, name: str) -> tuple[str, bool]:
    """Remove a key. The flag says whether anything was removed."""
    lines = text.splitlines()
    pattern = _key_re(name)
    for sec_name, start, end in _sections(lines):
        if sec_name != section:
            continue
        for i in range(start, end):
            m = pattern.match(lines[i])
            if m and not m.group(2):
                del lines[i]
                return _join(lines), True
    return text, False


def _insert_point(lines: list[str], start: int, end: int) -> int:
    """Just past the last meaningful line of a section, before its trailing blanks."""
    i = end
    while i > start and not lines[i - 1].strip():
        i -= 1
    return i


def _join(lines: list[str]) -> str:
    return "\n".join(lines).rstrip("\n") + "\n"
