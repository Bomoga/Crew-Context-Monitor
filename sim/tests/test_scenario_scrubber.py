from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import yaml

from ccm_sim.beats import rmssd
from ccm_sim.engine import World, build_world, run_world
from ccm_sim.messages import CABIN_TOPIC, SIM_EVENT_TOPIC, WEARABLE_TOPIC
from ccm_sim.scenario import ScenarioError, load_scenario
from ccm_sim.sinks import MemorySink, Record
from ccm_sim.thresholds import default_path, load_thresholds
from ccm_sim.timeutil import DEFAULT_START
from ccm_sim.units import ppm_to_mmhg

SEEDS = [1, 2, 3, 4, 5]
M = 60.0


def run(seed: int) -> tuple[World, list[Record]]:
    world = build_world(load_scenario("scrubber_failure"), seed, DEFAULT_START)
    sink = MemorySink()
    run_world(world, sink)
    return world, sink.records


def is_crew(r: Record, crew: str, lo: float, hi: float) -> bool:
    p = r.payload
    return r.topic == WEARABLE_TOPIC and p["crew"] == crew and lo <= p["t_meas"] < hi


def window_rmssd(records: list[Record], crew: str, lo: float, hi: float) -> float:
    rr: list[int] = []
    for r in records:
        if (
            r.topic == WEARABLE_TOPIC
            and r.payload["crew"] == crew
            and lo <= r.payload["t_meas"] < hi
        ):
            rr += r.payload["ibi"]
    return rmssd(np.array(rr))


def mean_field(records: list[Record], crew: str, field: str, lo: float, hi: float) -> float:
    vals = [
        r.payload[field]
        for r in records
        if r.topic == WEARABLE_TOPIC
        and r.payload["crew"] == crew
        and lo <= r.payload["t_meas"] < hi
    ]
    return float(np.mean(vals))


def test_events_are_the_three_documented_ones() -> None:
    world = build_world(load_scenario("scrubber_failure"), 1, DEFAULT_START)
    assert [(e.name, e.label, e.phase) for e in world.events] == [
        ("scrubber_fault", "Scrubber fault begins", "start"),
        ("co2_passes_yellow", "CO2 passes 2.5 mmHg", "mark"),
        ("co2_passes_red", "CO2 passes 3.0 mmHg", "mark"),
    ]
    assert world.missing_marks == []


@pytest.mark.parametrize("seed", SEEDS)
def test_co2_crosses_yellow_and_red_per_thresholds(seed: int) -> None:
    world, records = run(seed)
    thresholds = load_thresholds()
    cabin = [r.payload for r in records if r.topic == CABIN_TOPIC]
    t = np.array([c["t_meas"] for c in cabin])
    mmhg = np.array([ppm_to_mmhg(c["co2"], thresholds.cabin_pressure_mmhg) for c in cabin])
    smooth = np.convolve(mmhg, np.ones(6) / 6, mode="same")  # one-minute mean
    marks = {e.name: e.t for e in world.events if e.phase == "mark"}
    for name, level in (("co2_passes_yellow", "yellow"), ("co2_passes_red", "red")):
        crossed = t[np.argmax(smooth >= thresholds.co2_mmhg(level))]
        # truth omits the +-60 ppm diurnal term (about +-2.5 min of ramp) and noise
        assert abs(crossed - marks[name]) < 5 * M, (name, crossed - marks[name])
    assert smooth.max() >= 1.25 * thresholds.co2_mmhg("red")
    assert smooth[t < world.t0 + 25 * M].max() < thresholds.co2_mmhg("yellow")


def run_control(seed: int) -> list[Record]:
    """The same seed with nothing happening, so differences are exactly the scenario's effect."""
    world = build_world(
        load_scenario("quiet_day"), seed, DEFAULT_START, ["W1", "W2", "W3"], 4 * 3600.0
    )
    sink = MemorySink()
    run_world(world, sink)
    return sink.records


@pytest.mark.parametrize("seed", SEEDS)
def test_crew_response_starts_twenty_minutes_after_yellow(seed: int) -> None:
    world, records = run(seed)
    control = run_control(seed)
    t_yellow = next(e.t for e in world.events if e.name == "co2_passes_yellow")
    t_end = world.t0 + 4 * 3600.0
    for crew in world.crew:
        offset = world.truth.offset_series(f"crew.{crew}.rmssd", step=30.0)
        times = world.truth.times(30.0)
        onset = times[np.argmax(np.abs(offset) > 0.01 * 12.0)]
        assert abs((onset - t_yellow) - 20 * M) <= 3 * M, (crew, (onset - t_yellow) / M)
        fall = window_rmssd(control, crew, t_end - 20 * M, t_end) - window_rmssd(
            records, crew, t_end - 20 * M, t_end
        )
        assert fall > 6.0, (crew, fall)
        hr_up = mean_field(records, crew, "hr", t_end - 20 * M, t_end) - mean_field(
            control, crew, "hr", t_end - 20 * M, t_end
        )
        assert 4.0 < hr_up < 8.0, (crew, hr_up)
        # nothing changes before the response starts
        early = mean_field(records, crew, "hr", world.t0, t_yellow) - mean_field(
            control, crew, "hr", world.t0, t_yellow
        )
        assert abs(early) < 1.0, (crew, early)


def test_sim_events_reach_the_publisher_in_order() -> None:
    _, records = run(1)
    names = [r.payload["name"] for r in records if r.topic == SIM_EVENT_TOPIC]
    assert names == ["scrubber_fault", "co2_passes_yellow", "co2_passes_red"]


def test_yellow_above_the_ramp_peak_fails_with_a_clear_message(tmp_path: Path) -> None:
    data = yaml.safe_load(default_path().read_text(encoding="utf-8"))
    data["air"]["co2"]["yellow"]["value"] = 4.5  # above 1.3 x red = 3.9 mmHg
    bad = tmp_path / "thresholds.yaml"
    bad.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ScenarioError, match="thresholds.yaml"):
        build_world(
            load_scenario("scrubber_failure"), 1, DEFAULT_START, thresholds=load_thresholds(bad)
        )


def test_raising_red_keeps_the_ramp_crossing_red(tmp_path: Path) -> None:
    data = yaml.safe_load(default_path().read_text(encoding="utf-8"))
    data["air"]["co2"]["red"]["value"] = 3.4
    bad = tmp_path / "thresholds.yaml"
    bad.write_text(yaml.safe_dump(data), encoding="utf-8")
    world = build_world(
        load_scenario("scrubber_failure"), 1, DEFAULT_START, thresholds=load_thresholds(bad)
    )
    assert "co2_passes_red" in {e.name for e in world.events}
