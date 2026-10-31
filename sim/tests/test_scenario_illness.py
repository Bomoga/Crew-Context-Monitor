from __future__ import annotations

import numpy as np
import pytest

from ccm_sim.beats import rmssd
from ccm_sim.engine import build_world, run_world
from ccm_sim.messages import CABIN_TOPIC, WEARABLE_TOPIC
from ccm_sim.scenario import load_scenario
from ccm_sim.sinks import MemorySink, Record
from ccm_sim.thresholds import load_thresholds
from ccm_sim.timeutil import DEFAULT_START
from ccm_sim.units import ppm_to_mmhg

SEEDS = [1, 2, 3, 4, 5]
H = 3600.0
WINDOW = (5 * H, 8 * H)  # effect complete (ramp ends at 3 h; skin lag settles by about 4 h)


def generate(name: str, seed: int) -> list[Record]:
    sink = MemorySink()
    run_world(build_world(load_scenario(name), seed, DEFAULT_START), sink)
    return sink.records


def crew_msgs(records: list[Record], crew: str, lo: float, hi: float) -> list[dict[str, object]]:
    t0 = DEFAULT_START
    return [
        r.payload
        for r in records
        if r.topic == WEARABLE_TOPIC
        and r.payload["crew"] == crew
        and t0 + lo <= r.payload["t_meas"] < t0 + hi
    ]


def mean_of(msgs: list[dict[str, object]], field: str) -> float:
    return float(np.mean([m[field] for m in msgs]))  # type: ignore[arg-type]


def pooled_rmssd(msgs: list[dict[str, object]]) -> float:
    return rmssd(np.array([x for m in msgs for x in m["ibi"]]))  # type: ignore[attr-defined]


@pytest.fixture(scope="module", params=SEEDS)
def runs(request: pytest.FixtureRequest) -> tuple[list[Record], list[Record]]:
    seed = int(request.param)
    control = build_world(load_scenario("quiet_day"), seed, DEFAULT_START, duration=8 * H)
    sink = MemorySink()
    run_world(control, sink)
    return generate("individual_illness", seed), sink.records


def test_w2_shifts_as_specified_within_ten_percent(runs: tuple[list[Record], list[Record]]) -> None:
    ill, quiet = runs
    a, b = (crew_msgs(ill, "W2", *WINDOW), crew_msgs(quiet, "W2", *WINDOW))
    assert mean_of(a, "hr") - mean_of(b, "hr") == pytest.approx(12.0, rel=0.10)
    assert pooled_rmssd(a) - pooled_rmssd(b) == pytest.approx(-15.0, rel=0.10)
    assert mean_of(a, "skin_c") - mean_of(b, "skin_c") == pytest.approx(0.8, rel=0.10)


def test_w1_and_w3_stay_at_their_quiet_values(runs: tuple[list[Record], list[Record]]) -> None:
    ill, quiet = runs
    for crew in ("W1", "W3"):
        a, b = crew_msgs(ill, crew, 0, 8 * H), crew_msgs(quiet, crew, 0, 8 * H)
        assert abs(mean_of(a, "hr") - mean_of(b, "hr")) < 1.0
        assert abs(pooled_rmssd(a) - pooled_rmssd(b)) < 3.0


def test_cabin_stays_normal(runs: tuple[list[Record], list[Record]]) -> None:
    ill, _ = runs
    thresholds = load_thresholds()
    cabin = [r.payload for r in ill if r.topic == CABIN_TOPIC]
    assert max(ppm_to_mmhg(c["co2"], thresholds.cabin_pressure_mmhg) for c in cabin) < 2.0
    assert thresholds.value("thermal.cabin_temp_c.lo") < min(c["temp_c"] for c in cabin)
    assert max(c["temp_c"] for c in cabin) < thresholds.value("thermal.cabin_temp_c.hi")


def test_only_w2_is_named_in_the_event() -> None:
    world = build_world(load_scenario("individual_illness"), 1, DEFAULT_START)
    assert [(e.name, e.crew, e.phase) for e in world.events] == [("w2_illness", "W2", "start")]
