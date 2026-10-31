import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import pytest

from ccm_sim.engine import build_world, run_world
from ccm_sim.messages import CABIN_TOPIC, WEARABLE_TOPIC
from ccm_sim.scenario import load_scenario
from ccm_sim.sinks import Record
from ccm_sim.timeutil import DEFAULT_START


@dataclass
class CountingSink:
    counts: Counter[str] = field(default_factory=Counter)
    crew: Counter[str] = field(default_factory=Counter)

    def open_node(
        self, key: str, will_topic: str | None, will_payload: dict[str, Any] | None
    ) -> None:
        return None

    def publish(self, record: Record) -> None:
        self.counts[record.topic] += 1
        if record.topic == WEARABLE_TOPIC:
            self.crew[record.payload["crew"]] += 1

    def close(self) -> None:
        return None


@pytest.mark.slow
def test_quiet_week_generates_in_under_two_minutes() -> None:
    sink = CountingSink()
    started = time.time()
    run_world(build_world(load_scenario("quiet_week"), 1, DEFAULT_START), sink)
    elapsed = time.time() - started
    assert elapsed < 120
    per_crew = 7 * 86400 // 5
    assert sink.crew == {"W1": per_crew, "W2": per_crew, "W3": per_crew}
    assert sink.counts[CABIN_TOPIC] == 7 * 86400 // 10
