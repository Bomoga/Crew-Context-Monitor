"""The mock Earth queue: summaries waiting for crew approval before the next comms window."""

from __future__ import annotations

import json
import math
from typing import Any

TIERS = ("crew_only", "flight_surgeon", "urgent")
WINDOW_S = 1800.0  # a comms window every 30 simulated minutes
RED_TIER = {
    "cardio": "crew_only",
    "air": "flight_surgeon",
    "thermal": "flight_surgeon",
    "radiation": "urgent",
}


def payload_bytes(payload: dict[str, Any]) -> int:
    return len(json.dumps(payload, separators=(",", ":")).encode("utf-8"))


class EarthQueue:
    """Items, their approval state, and which comms window has carried them."""

    def __init__(self, t0: float, auto_approve: dict[str, bool], baseline_sentence: str) -> None:
        self.t0 = t0
        self._items: list[dict[str, Any]] = []
        self._approved_t: dict[str, float] = {}
        self._queued_red: set[tuple[str, float]] = set()
        self._n = 0
        seeds = [
            ("crew_only", "Daily crew summary", baseline_sentence),
            (
                "flight_surgeon",
                "Weekly baseline report",
                "Weekly baseline report: 3 crew, no changes in 7 days.",
            ),
            ("urgent", "Urgent channel check", "Urgent channel check: 0 alerts waiting."),
        ]
        for tier, kind, summary in seeds:
            self.add(
                t0,
                tier,
                summary,
                {"type": kind.lower().replace(" ", "_"), "summary": summary},
                auto_approve,
            )

    def add(
        self,
        t: float,
        tier: str,
        summary: str,
        payload: dict[str, Any],
        auto_approve: dict[str, bool],
    ) -> dict[str, Any]:
        self._n += 1
        item = {
            "id": f"q-{self._n}",
            "t": t,
            "tier": tier,
            "approved": False,
            "sent": False,
            "bytes": payload_bytes(payload),
            "summary": summary,
            "payload": payload,
        }
        self._items.append(item)
        if auto_approve.get(tier, False):
            self._approve(item, t)
        return item

    def queue_red(
        self, domain: str, t_from: float, summary: str, auto_approve: dict[str, bool]
    ) -> bool:
        """Queue a summary for a card that turned red at ``t_from``; False if already queued."""
        key = (domain, t_from)
        if key in self._queued_red:
            return False
        self._queued_red.add(key)
        payload = {"domain": domain, "level": "red", "t": int(t_from), "summary": summary}
        self.add(t_from, RED_TIER[domain], summary, payload, auto_approve)
        return True

    def _approve(self, item: dict[str, Any], t: float) -> None:
        if not item["approved"]:
            item["approved"] = True
            self._approved_t[item["id"]] = t

    def approve(self, item_id: str, t_now: float) -> dict[str, Any] | None:
        """Approve an item; approving twice changes nothing. None if there is no such item."""
        for item in self._items:
            if item["id"] == item_id:
                self._approve(item, t_now)
                return self._view_item(item, t_now)
        return None

    def next_window(self, t_now: float) -> float:
        return self.t0 + (math.floor((t_now - self.t0) / WINDOW_S) + 1) * WINDOW_S

    def _view_item(self, item: dict[str, Any], t_now: float) -> dict[str, Any]:
        out = dict(item)
        approved_t = self._approved_t.get(item["id"])
        if approved_t is not None:
            # carried by the first comms window strictly after approval
            window = self.next_window(approved_t)
            out["sent"] = window <= t_now
        return out

    def view(self, t_now: float) -> dict[str, Any]:
        return {
            "next_window_t": self.next_window(t_now),
            "items": [self._view_item(i, t_now) for i in self._items],
        }
