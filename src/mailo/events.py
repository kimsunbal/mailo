"""The event model — four events, ordered by cost (DESIGN.md §3)."""

from __future__ import annotations

from enum import StrEnum


class Event(StrEnum):
    """Something worth interrupting a human for.

    The declaration order is the order of **what it costs to miss them**.
    `blocked` costs the most: thirty seconds of attention would clear it, and
    instead thirty minutes are lost.
    """

    BLOCKED = "blocked"
    FAILED = "failed"
    DONE = "done"
    CUSTOM = "custom"

    @property
    def emoji(self) -> str:
        """Marker prefixed to the mail subject (§8.1)."""
        return _EMOJI[self]

    @property
    def color(self) -> int:
        """Colour bar on the Discord embed (§8.1).

        Hex literals only. `json.dumps` serialises these to decimal on its own,
        so there is no reason to write a hand-converted decimal alongside —
        converting by hand is how you get it wrong.
        """
        return _COLOR[self]

    @property
    def label(self) -> str:
        return _LABEL[self]


_EMOJI: dict[Event, str] = {
    Event.BLOCKED: "⏸️",
    Event.FAILED: "❌",
    Event.DONE: "✅",
    Event.CUSTOM: "🔔",
}

_COLOR: dict[Event, int] = {
    Event.BLOCKED: 0xE8A33D,
    Event.FAILED: 0xD64545,
    Event.DONE: 0x4CAF50,
    Event.CUSTOM: 0x8A8A8A,
}

_LABEL: dict[Event, str] = {
    Event.BLOCKED: "waiting for input",
    Event.FAILED: "failed",
    Event.DONE: "done",
    Event.CUSTOM: "notice",
}
