"""Every scenario x 5 seeds: expectations are consistent and a stretch of output is schema-valid.

Marked ``slow``; ``make sim-eval`` runs it together with the per-scenario physics tests.
"""

from __future__ import annotations

import pytest

from ccm_sim import contracts
from ccm_sim.engine import build_world, run_world
from ccm_sim.expectations import check_expectations
from ccm_sim.messages import CABIN_TOPIC, SIM_EVENT_TOPIC, WEARABLE_TOPIC
from ccm_sim.scenario import list_scenarios, load_scenario
from ccm_sim.sinks import MemorySink
from ccm_sim.timeutil import DEFAULT_START

SEEDS = [1, 2, 3, 4, 5]
KIND = {
    WEARABLE_TOPIC: "wearable_telemetry",
    CABIN_TOPIC: "cabin_telemetry",
    SIM_EVENT_TOPIC: "sim_event",
}


@pytest.mark.slow
@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("name", list_scenarios())
def test_scenario_is_consistent_and_publishes_valid_messages(name: str, seed: int) -> None:
    world = build_world(load_scenario(name), seed, DEFAULT_START)
    assert check_expectations(world) == []
    short = build_world(
        load_scenario(name), seed, DEFAULT_START, duration=min(world.duration, 3600.0)
    )
    sink = MemorySink()
    run_world(short, sink)
    for record in sink.records:
        kind = KIND.get(record.topic, "node_status")
        contracts.validate(kind, record.payload)
