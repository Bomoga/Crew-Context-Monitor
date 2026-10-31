from __future__ import annotations

import numpy as np
import pytest

from ccm_sim.engine import World, build_world, run_world
from ccm_sim.messages import CABIN_TOPIC, WEARABLE_TOPIC
from ccm_sim.scenario import Scenario, load_scenario
from ccm_sim.sinks import MemorySink, Record
from ccm_sim.thresholds import load_thresholds
from ccm_sim.timeutil import DEFAULT_START
from ccm_sim.units import mmhg_to_ppm

M = 60.0


def generate(scenario: Scenario, seed: int = 1) -> tuple[World, list[Record]]:
    world = build_world(scenario, seed, DEFAULT_START)
    sink = MemorySink()
    run_world(world, sink)
    return world, sink.records


def without_event(name: str) -> Scenario:
    scenario = load_scenario("coincident_trends")
    scenario.events = [e for e in scenario.events if e.name != name]
    return scenario


def test_co2_stays_below_yellow() -> None:
    world, records = generate(load_scenario("coincident_trends"))
    yellow_ppm = mmhg_to_ppm(load_thresholds().co2_mmhg("yellow"))
    assert world.truth.series("cabin.co2").max() == pytest.approx(1300.0)
    assert max(r.payload["co2"] for r in records if r.topic == CABIN_TOPIC) < 0.5 * yellow_ppm


def test_w3_trend_starts_thirty_minutes_before_the_co2_trend() -> None:
    world, _ = generate(load_scenario("coincident_trends"))
    times = world.truth.times(30.0)
    hr = world.truth.offset_series("crew.W3.hr", step=30.0)
    co2 = world.truth.offset_series("cabin.co2", step=30.0)
    hr_start, co2_start = times[np.argmax(hr > 0)], times[np.argmax(co2 > 0)]
    assert co2_start - hr_start == pytest.approx(30 * M, abs=30.0)
    assert hr.max() == pytest.approx(6.0, abs=0.05)


def test_truth_channels_have_no_coupling() -> None:
    world, _ = generate(load_scenario("coincident_trends"))
    assert all(e.op != "coupled" for e in world.truth.effects)
    for crew in ("W1", "W2"):
        for field in ("hr", "rmssd", "skin", "spo2", "act"):
            assert not world.truth.offset_series(f"crew.{crew}.{field}").any()
    assert not world.truth.offset_series("crew.W3.rmssd").any()
    assert not world.truth.offset_series("cabin.temp").any()


def test_the_two_trends_are_statistically_independent() -> None:
    both_world, both = generate(load_scenario("coincident_trends"))
    _, hr_only = generate(without_event("co2_trend"))
    _, co2_only = generate(without_event("w3_hr_trend"))

    def w3(records: list[Record]) -> list[dict[str, object]]:
        return [
            r.payload for r in records if r.topic == WEARABLE_TOPIC and r.payload["crew"] == "W3"
        ]

    def cabin(records: list[Record]) -> list[dict[str, object]]:
        return [r.payload for r in records if r.topic == CABIN_TOPIC]

    assert w3(both) == w3(hr_only)  # removing the CO2 trend does not change W3
    assert cabin(both) == cabin(co2_only)  # removing the HR trend does not change the cabin
    assert both_world.missing_marks == []
