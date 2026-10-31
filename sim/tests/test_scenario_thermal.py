from __future__ import annotations

import numpy as np
import pytest

from ccm_sim.engine import World, build_world, run_world
from ccm_sim.messages import CABIN_TOPIC, WEARABLE_TOPIC, WearableNode
from ccm_sim.publisher import NodeSource
from ccm_sim.scenario import load_scenario
from ccm_sim.sinks import MemorySink, Record
from ccm_sim.thresholds import load_thresholds
from ccm_sim.timeutil import DEFAULT_START

SEEDS = [1, 2, 3, 4, 5]
M = 60.0
HOURS5 = 5 * 3600.0


def generate(name: str, seed: int) -> tuple[World, list[Record]]:
    world = build_world(load_scenario(name), seed, DEFAULT_START, duration=HOURS5)
    sink = MemorySink()
    run_world(world, sink)
    return world, sink.records


def minute_series(records: list[Record], crew: str | None, field: str) -> np.ndarray:
    n = int(HOURS5 // M)
    sums, counts = np.zeros(n), np.zeros(n)
    for r in records:
        p = r.payload
        if (
            crew is None
            and r.topic == CABIN_TOPIC
            or crew is not None
            and r.topic == WEARABLE_TOPIC
            and p["crew"] == crew
        ):
            k = int((p["t_meas"] - DEFAULT_START - 1e-6) // M)
            if 0 <= k < n:
                sums[k] += p[field]
                counts[k] += 1
    return sums / counts


@pytest.mark.parametrize("seed", SEEDS)
def test_cabin_leaves_the_band_at_the_expected_time(seed: int) -> None:
    world, records = generate("thermal_fault", seed)
    hi = load_thresholds().value("thermal.cabin_temp_c.hi")
    t_mark = next(e.t for e in world.events if e.name == "temp_passes_hi")
    # 27 C is reached 5/7 of the way through the 2 h ramp that starts at 30 min
    assert t_mark - world.t0 == pytest.approx((30 + 120 * 5 / 7) * M, abs=M)
    temp = minute_series(records, None, "temp_c")
    smooth = np.convolve(temp, np.ones(3) / 3, mode="same")
    crossed = int(np.argmax(smooth[2:-2] > hi)) + 2
    assert abs(crossed * M - (t_mark - world.t0)) <= 5 * M
    assert smooth[: int(30 * M / M)].max() < hi - 3


@pytest.mark.parametrize("seed", SEEDS)
def test_skin_follows_cabin_through_the_lag(seed: int) -> None:
    world, records = generate("thermal_fault", seed)
    _, control = generate("quiet_day", seed)
    gain, tau = 0.25, 1200.0
    cabin_off = world.truth.offset_series("cabin.temp", step=M)
    # first-order lag of gain * cabin offset, stepped each minute
    pred = np.zeros_like(cabin_off)
    a = 1.0 - np.exp(-M / tau)
    for k in range(1, len(pred)):
        pred[k] = pred[k - 1] + a * (gain * cabin_off[k] - pred[k - 1])
    measured = minute_series(records, "W1", "skin_c") - minute_series(control, "W1", "skin_c")
    n = min(len(measured), len(pred) - 1)
    assert np.abs(measured[:n] - pred[1 : n + 1]).max() < 0.12


@pytest.mark.parametrize("seed", SEEDS)
def test_hr_changes_only_through_the_model(seed: int) -> None:
    world = build_world(load_scenario("thermal_fault"), seed, DEFAULT_START, duration=HOURS5)
    nodes = [s.node for s in world.sources if isinstance(s, NodeSource)]
    node = next(n for n in nodes if isinstance(n, WearableNode) and n.crew == "W2")
    hr: list[float] = []
    model: list[float] = []
    previous = node.physiology.advance_to(world.t0).hr_model
    while node.next_t <= world.t0 + HOURS5:
        msg = node.next_message()
        hr.append(float(msg["hr"]))
        model.append(previous)
        previous = node.physiology.advance_to(float(msg["t_meas"])).hr_model
    per = 60  # five-minute means; see D23
    k = len(hr) // per * per
    hr_min = np.array(hr[:k]).reshape(-1, per).mean(axis=1)
    model_min = np.array(model[:k]).reshape(-1, per).mean(axis=1)
    assert np.abs(hr_min - model_min).max() <= 3.0
    # beta2 does the work: the model's rise net of the circadian term is beta2 * 7 C
    t_end = world.t0 + HOURS5
    circ = node.physiology.circadian_hr(t_end) - node.physiology.circadian_hr(world.t0)
    rise = np.mean(model[-per:]) - np.mean(model[:per]) - circ
    assert rise == pytest.approx(node.physiology.p["beta2"] * 7.0, abs=1.0)
