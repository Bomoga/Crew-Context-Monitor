"""One test per effect op, plus scenario loading, events, marks and wildcard handling."""

from __future__ import annotations

import copy
from typing import Any

import numpy as np
import pytest

from ccm_sim import contracts
from ccm_sim.engine import World, build_world, run_world
from ccm_sim.messages import SIM_EVENT_TOPIC, WEARABLE_TOPIC
from ccm_sim.scenario import (
    ScenarioError,
    list_scenarios,
    load_scenario,
    scenario_from_dict,
)
from ccm_sim.sinks import MemorySink
from ccm_sim.thresholds import load_thresholds
from ccm_sim.units import mmhg_to_ppm

T0 = 20740 * 86400.0  # a whole number of days after the epoch: time of day starts at 00:00 UTC
H = 3600.0
M = 60.0


def scen(
    events: list[dict[str, Any]],
    duration: str = "4h",
    crew: list[str] | None = None,
    marks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "name": "t",
        "title": "test",
        "duration": duration,
        "crew": crew or ["W1", "W2"],
        "events": events,
        "marks": marks or [],
        "expect": [],
    }


def event(
    *effects: dict[str, Any],
    at: str = "10m",
    name: str = "ev",
    label: str = "Thing begins",
    **extra: Any,
) -> dict[str, Any]:
    return {"at": at, "name": name, "label": label, "effects": list(effects), **extra}


def world(raw: dict[str, Any], crew: list[str] | None = None, seed: int = 1) -> World:
    return build_world(scenario_from_dict(raw), seed, T0, crew)


def test_set_holds_target_at_a_value() -> None:
    w = world(scen([event({"target": "crew.W1.hr", "op": "set", "value": 80, "for": "1h"})]))
    assert w.truth.offset("crew.W1.hr", T0 + 9 * M) == 0.0
    assert w.truth.offset("crew.W1.hr", T0 + 30 * M) == pytest.approx(80 - 62)
    assert w.truth.level("crew.W1.hr", T0 + 30 * M) == pytest.approx(80)
    assert w.truth.offset("crew.W1.hr", T0 + 71 * M) == 0.0
    assert w.truth.offset("crew.W2.hr", T0 + 30 * M) == 0.0


def test_step_adds_delta_for_a_duration() -> None:
    w = world(scen([event({"target": "cabin.temp", "op": "step", "delta": 3, "for": "30m"})]))
    assert w.truth.offset("cabin.temp", T0 + 5 * M) == 0.0
    assert w.truth.offset("cabin.temp", T0 + 20 * M) == 3.0
    assert w.truth.offset("cabin.temp", T0 + 41 * M) == 0.0


def test_ramp_to_threshold_reference_is_linear_then_holds() -> None:
    ramp = {
        "target": "cabin.co2",
        "op": "ramp",
        "to": {"threshold": "air.co2.red", "factor": 1.3},
        "over": "3h",
    }
    w = world(scen([event(ramp, at="30m")], duration="4h"))
    top = 1.3 * mmhg_to_ppm(load_thresholds().co2_mmhg("red"))
    assert top == pytest.approx(5131.6, abs=1.0)
    assert w.truth.level("cabin.co2", T0 + 29 * M) == pytest.approx(800)
    assert w.truth.level("cabin.co2", T0 + 30 * M + 1.5 * H) == pytest.approx((800 + top) / 2)
    assert w.truth.level("cabin.co2", T0 + 3.5 * H) == pytest.approx(top)
    assert w.truth.level("cabin.co2", T0 + 3.9 * H) == pytest.approx(top)


def test_ramp_shows_up_in_generated_cabin_data() -> None:
    def cabin_co2(effects: list[dict[str, Any]]) -> list[int]:
        sink = MemorySink()
        run_world(world(scen(effects, duration="1h", crew=["W1"])), sink)
        return [r.payload["co2"] for r in sink.records if r.topic.endswith("cabin/telemetry")]

    ramp = event({"target": "cabin.co2", "op": "ramp", "to": 2000, "over": "20m"})
    shifted, quiet = cabin_co2([ramp]), cabin_co2([])
    assert abs(np.mean(shifted[-30:]) - np.mean(quiet[-30:]) - 1200) < 40
    assert abs(np.mean(shifted[:30]) - np.mean(quiet[:30])) < 5


def test_drift_per_day_is_linear_and_caps_at_days() -> None:
    drift = {"target": "crew.W1.hr", "op": "drift_per_day", "delta": 1, "days": 3}
    w = world(scen([event(drift, at="0s")], duration="5d"))
    assert w.truth.offset("crew.W1.hr", T0 + 1.5 * 86400) == pytest.approx(1.5)
    assert w.truth.offset("crew.W1.hr", T0 + 4 * 86400) == pytest.approx(3.0)


def coupled_scenario() -> dict[str, Any]:
    ramp = {
        "target": "cabin.co2",
        "op": "ramp",
        "to": {"threshold": "air.co2.red", "factor": 1.3},
        "over": "3h",
    }
    coupled = {
        "target": "crew.*.rmssd",
        "op": "coupled",
        "driver": "cabin.co2",
        "start": {"above_threshold": "air.co2.yellow", "lag": "20m"},
        "gain_at_peak": -12,
    }
    return scen([event(ramp, coupled, at="30m")])


def test_coupled_follows_driver_excess_after_the_lag() -> None:
    w = world(coupled_scenario())
    t_yellow = w.truth.first_time("cabin.co2 >= air.co2.yellow")
    assert t_yellow is not None
    assert w.truth.offset("crew.W1.rmssd", t_yellow + 19 * M) == pytest.approx(0.0, abs=1e-9)
    assert w.truth.offset("crew.W1.rmssd", t_yellow + 21 * M) < -0.05
    assert w.truth.offset("crew.W2.rmssd", T0 + 3.9 * H) == pytest.approx(-12.0, abs=0.01)
    assert w.truth.offset("crew.W1.rmssd", T0 + 20 * M) == 0.0


def test_coupled_fails_clearly_when_the_driver_never_crosses() -> None:
    ramp = {"target": "cabin.co2", "op": "ramp", "to": 1200, "over": "3h"}
    coupled = {
        "target": "crew.W1.hr",
        "op": "coupled",
        "driver": "cabin.co2",
        "start": {"above_threshold": "air.co2.yellow"},
        "gain_at_peak": 5,
    }
    with pytest.raises(ScenarioError, match="thresholds.yaml"):
        world(scen([event(ramp, coupled)]))


def test_exercise_raises_activity_for_the_block() -> None:
    ex = {"target": "crew.W1.act", "op": "exercise", "act": 1.2, "for": "30m", "recovery_tau": "3m"}
    w = world(scen([event(ex)]))
    assert w.truth.level("crew.W1.act", T0 + 20 * M) == pytest.approx(1.2)
    assert w.truth.level("crew.W1.act", T0 + 45 * M) == pytest.approx(0.06)


def test_rate_changes_the_geiger_rate() -> None:
    w = world(scen([event({"target": "cabin.cpm", "op": "rate", "cpm": 240, "for": "40m"})]))
    assert w.truth.level("cabin.cpm", T0 + 20 * M) == pytest.approx(240)
    assert w.truth.level("cabin.cpm", T0 + 51 * M) == pytest.approx(18)


def test_silence_is_recorded_for_the_publisher() -> None:
    w = world(scen([event({"op": "silence", "node": "C1", "for": "8m", "buffer": True})]))
    assert [(s.node, s.t_start, s.t_end, s.buffer) for s in w.truth.silences] == [
        ("C1", T0 + 10 * M, T0 + 18 * M, True)
    ]


def test_wildcard_expands_over_the_run_crew_and_skips_absent_crew() -> None:
    raw = scen(
        [
            event(
                {"target": "crew.*.hr", "op": "step", "delta": 5, "for": "1h"},
                {"target": "crew.W2.rmssd", "op": "step", "delta": -3, "for": "1h"},
            )
        ],
        crew=["W1", "W2", "W3"],
    )
    w = world(raw, crew=["W1", "W3"])
    at = T0 + 20 * M
    assert w.truth.offset("crew.W1.hr", at) == 5 and w.truth.offset("crew.W3.hr", at) == 5
    assert w.truth.offset("crew.W2.hr", at) == 0
    assert w.truth.offset("crew.W2.rmssd", at) == 0


def test_events_marks_and_labels_are_published_in_order() -> None:
    ramp = {
        "target": "cabin.co2",
        "op": "ramp",
        "to": {"threshold": "air.co2.red", "factor": 1.3},
        "over": "3h",
    }
    step = {"target": "crew.W2.hr", "op": "step", "delta": 4, "for": "20m"}
    raw = scen(
        [
            event(ramp, at="30m", name="fault", label="Fault begins"),
            event(step, at="1h", name="bump", label="HR bump begins"),
        ],
        marks=[
            {
                "when": "cabin.co2 >= air.co2.yellow",
                "name": "passes_yellow",
                "label": "CO2 passes {air.co2.yellow} mmHg",
            }
        ],
    )
    sink = MemorySink()
    w = world(raw)
    run_world(w, sink)
    events = [r.payload for r in sink.records if r.topic == SIM_EVENT_TOPIC]
    for payload in events:
        contracts.validate("sim_event", payload)
    assert [e["name"] for e in events] == ["fault", "bump", "bump_end", "passes_yellow"]
    assert events[2]["label"] == "HR bump ends" and events[2]["crew"] == "W2"
    assert events[3]["label"] == "CO2 passes 2.5 mmHg" and events[3]["phase"] == "mark"
    assert [e["t_meas"] for e in events] == sorted(e["t_meas"] for e in events)
    assert events[0]["crew"] is None


def test_unbounded_event_has_no_end_event() -> None:
    ramp = {"target": "cabin.co2", "op": "ramp", "to": 2000, "over": "1h"}
    w = world(scen([event(ramp)]))
    assert [e.phase for e in w.events] == ["start"]


@pytest.mark.parametrize(
    "bad",
    [
        {"op": "teleport", "target": "cabin.co2"},
        {"op": "step", "target": "cabin.co2", "delta": 1},
        {"op": "step", "target": "cabin.nope", "delta": 1, "for": "5m"},
        {"op": "step", "delta": 1, "for": "5m"},
        {"op": "step", "target": "cabin.co2", "delta": 1, "for": "soon"},
    ],
)
def test_bad_effects_are_rejected(bad: dict[str, Any]) -> None:
    with pytest.raises((ScenarioError, ValueError)):
        world(scen([event(copy.deepcopy(bad))]))


def test_scenario_files_load_and_quiet_alias_works() -> None:
    assert {"quiet_day", "quiet_week"} <= set(list_scenarios())
    assert load_scenario("quiet").name == "quiet_day"
    week = load_scenario("quiet_week")
    assert week.duration == 7 * 86400 and week.crew == ["W1", "W2", "W3"]
    with pytest.raises(ScenarioError):
        load_scenario("no_such_scenario")


def test_applied_offsets_reach_the_wearable_messages() -> None:
    def mean_hr(effects: list[dict[str, Any]]) -> float:
        sink = MemorySink()
        run_world(world(scen(effects, duration="30m", crew=["W1"])), sink)
        hr = [r.payload["hr"] for r in sink.records if r.topic == WEARABLE_TOPIC]
        return float(np.mean(hr[60:]))

    shifted = mean_hr([event({"target": "crew.W1.hr", "op": "set", "value": 100}, at="0s")])
    quiet = mean_hr([])
    assert abs((shifted - quiet) - (100 - 62)) < 1.5
