from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from ccm_sim.beats import rmssd
from ccm_sim.engine import build_world, run_world
from ccm_sim.messages import WEARABLE_TOPIC
from ccm_sim.scenario import load_scenario
from ccm_sim.sinks import MemorySink, Record
from ccm_sim.timeutil import DEFAULT_START

SEEDS = [1, 2, 3, 4, 5]
DAY = 86400.0
WIN = 300.0


def test_truth_slopes_and_w1_only() -> None:
    world = build_world(load_scenario("sleep_debt_drift"), 1, DEFAULT_START)
    t0 = world.t0
    assert world.truth.offset("crew.W1.hr", t0 + 3 * DAY) == pytest.approx(3.0)
    assert world.truth.offset("crew.W1.rmssd", t0 + 3 * DAY) == pytest.approx(-9.0)
    assert world.truth.offset("crew.W1.hr", t0 + 5.9 * DAY) == pytest.approx(5.9)
    for crew in ("W2", "W3"):
        assert not world.truth.offset_series(f"crew.{crew}.hr", step=3600.0).any()
    assert [e.phase for e in world.events] == ["start"]


def windows(records: list[Record], crew: str, field: str) -> np.ndarray:
    """Per 5-minute window: mean HR, or RMSSD of the window's pooled intervals."""
    buckets: dict[int, list[dict[str, Any]]] = {}
    for r in records:
        if r.topic == WEARABLE_TOPIC and r.payload["crew"] == crew:
            buckets.setdefault(int((r.payload["t_meas"] - DEFAULT_START - 1e-6) // WIN), []).append(
                r.payload
            )
    out = []
    for k in sorted(buckets):
        msgs = buckets[k]
        if field == "hr":
            out.append(np.mean([m["hr"] for m in msgs]))
        else:
            out.append(rmssd(np.array([x for m in msgs for x in m["ibi"]])))
    return np.array(out)


def generate(name: str, seed: int) -> list[Record]:
    world = build_world(load_scenario(name), seed, DEFAULT_START, ["W1"], 6 * DAY)
    sink = MemorySink()
    run_world(world, sink)
    return sink.records


@pytest.mark.slow
@pytest.mark.parametrize("seed", SEEDS)
def test_measured_slopes_and_no_spikes(seed: int) -> None:
    drift, quiet = generate("sleep_debt_drift", seed), generate("quiet_day", seed)
    hr_d, hr_q = windows(drift, "W1", "hr"), windows(quiet, "W1", "hr")
    rm_d, rm_q = windows(drift, "W1", "rmssd"), windows(quiet, "W1", "rmssd")
    n = min(len(hr_d), len(hr_q))
    days = (np.arange(n) + 0.5) * WIN / DAY
    hr_slope = np.polyfit(days, (hr_d - hr_q)[:n], 1)[0]
    rm_slope = np.polyfit(days, (rm_d - rm_q)[:n], 1)[0]
    assert hr_slope == pytest.approx(1.0, rel=0.2)
    assert rm_slope == pytest.approx(-3.0, rel=0.2)
    # no single window departs from the drifting mean by more than the quiet-day spread
    truth_hr = days * 1.0
    residual = (hr_d - hr_q)[:n] - truth_hr
    spread = float(np.std(hr_q[:288] - hr_q[:288].mean()))
    assert np.abs(residual).max() < spread, (np.abs(residual).max(), spread)
