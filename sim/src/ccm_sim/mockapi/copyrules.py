"""The copy rules for every user-visible string, as a checker (PLAN P6).

- No "caused by": say "consistent with".
- No z-scores or raw z values.
- Heart-rate variability is always "pulse-rate variability": the abbreviation HRV never appears.
- Anything about radiation says it is a "proxy".
- A reason is one plain sentence with a number in it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

_CAUSED = re.compile(r"\bcaus(?:ed|es|ing)\s+by\b", re.IGNORECASE)
_Z = re.compile(r"\bz[- ]?scores?\b|\bz\s*[=:≈]\s*[-+]?\d", re.IGNORECASE)
_HRV = re.compile(r"\bHRV\b", re.IGNORECASE)
_RADIATION = re.compile(r"\bradiation\b", re.IGNORECASE)
_DIGIT = re.compile(r"\d")


def violations(text: str, *, reason: bool = False) -> list[str]:
    """Return the copy rules ``text`` breaks (empty when it is clean)."""
    found: list[str] = []
    if _CAUSED.search(text):
        found.append('uses "caused by" (write "consistent with")')
    if _Z.search(text):
        found.append("shows a z-score")
    if _HRV.search(text):
        found.append('uses "HRV" (write "pulse-rate variability")')
    if _RADIATION.search(text) and "proxy" not in text.lower():
        found.append('mentions radiation without "proxy"')
    if reason and not _DIGIT.search(text):
        found.append("a reason needs a number")
    if reason and text.count("\n"):
        found.append("a reason is one plain sentence")
    return found


def status_strings(status: dict[str, Any]) -> Iterable[tuple[str, str, bool]]:
    """Yield ``(where, text, is_reason)`` for each user-visible string in a status response."""
    cs = status["crew_status"]
    yield "crew_status.sentence", cs["sentence"], True
    if cs["action"]:
        yield "crew_status.action", cs["action"], False
    for card in status["cards"]:
        d = card["domain"]
        yield f"cards.{d}.reason", card["reason"], True
        if card["action"]:
            yield f"cards.{d}.action", card["action"], False
        yield f"cards.{d}.detector.detail", card["detector"]["detail"], False
        for number in card["numbers"]:
            yield f"cards.{d}.numbers.{number['label']}", number["label"], False
    if status["correlation"]:
        yield "correlation.sentence", status["correlation"]["sentence"], True


def event_strings(events: dict[str, Any]) -> Iterable[tuple[str, str, bool]]:
    for e in events["events"]:
        yield f"events.{e['id']}", e["sentence"], False


def queue_strings(queue: dict[str, Any]) -> Iterable[tuple[str, str, bool]]:
    for item in queue["items"]:
        yield f"queue.{item['id']}.summary", item["summary"], False
