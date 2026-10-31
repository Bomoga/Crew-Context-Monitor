"""Small time helpers shared by the CLI and the scenario engine."""

from __future__ import annotations

import re
from datetime import UTC, datetime

_UNITS = {"s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}
_DURATION = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([smhd]?)\s*$")


def parse_duration(text: str | float | int) -> float:
    """Parse ``"90s"``, ``"30m"``, ``"2h"``, ``"7d"`` or a plain number of seconds."""
    if isinstance(text, int | float):
        return float(text)
    match = _DURATION.match(text)
    if not match:
        raise ValueError(f"cannot parse duration {text!r}")
    return float(match.group(1)) * _UNITS[match.group(2) or "s"]


def parse_iso(text: str) -> float:
    """Parse an ISO 8601 timestamp (``Z`` allowed) to unix seconds; naive means UTC."""
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.timestamp()


DEFAULT_START = parse_iso("2026-11-01T00:00:00Z")
