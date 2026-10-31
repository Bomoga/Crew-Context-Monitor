from __future__ import annotations

import numpy as np
import pytest

from ccm_sim.engine import build_world
from ccm_sim.messages import WearableNode
from ccm_sim.publisher import NodeSource
from ccm_sim.scenario import load_scenario
from ccm_sim.timeutil import DEFAULT_START

SEEDS = [1, 2, 3, 4, 5]
M = 60.0


def run_w1(seed: int) -> tuple[list[dict[str, object]], list[float]]:
    """Step W1's wearable node alone and collect messages with the model's HR at each time."""
    world = build_world(load_scenario("exercise_block"), seed, DEFAULT_START)
    nodes = [s.node for s in world.sources if isinstance(s, NodeSource)]
    node = next(n for n in nodes if isinstance(n, WearableNode) and n.crew == "W1")
    assert isinstance(node, WearableNode)
    msgs: list[dict[str, object]] = []
    model: list[float] = []
    previous = node.physiology.advance_to(world.t0).hr_model
    while node.next_t <= world.t0 + world.duration:
        msg = node.next_message()
        msgs.append(msg)
        now = node.physiology.advance_to(float(msg["t_meas"])).hr_model  # type: ignore[arg-type]
        # beats in a 5 s window are driven by the state held from the window start
        model.append(previous)
        previous = now
    return msgs, model


def minute_means(values: list[float], per_minute: int = 12) -> np.ndarray:
    arr = np.array(values[: len(values) // per_minute * per_minute], dtype=float)
    return arr.reshape(-1, per_minute).mean(axis=1)


@pytest.mark.parametrize("seed", SEEDS)
def test_hr_peaks_near_150_and_the_model_explains_it(seed: int) -> None:
    msgs, model = run_w1(seed)
    hr = [float(m["hr"]) for m in msgs]  # type: ignore[arg-type]
    hr_min, model_min = minute_means(hr), minute_means(model)
    assert abs(hr_min.max() - 150.0) <= 8.0, hr_min.max()
    assert np.abs(hr_min - model_min).max() <= 5.0, np.abs(hr_min - model_min).max()
    # back near rest ten minutes after the block ends
    assert hr_min[70:80].mean() < 75.0


@pytest.mark.parametrize("seed", SEEDS)
def test_motion_flag_is_true_through_the_block(seed: int) -> None:
    msgs, _ = run_w1(seed)
    t0 = DEFAULT_START
    block = [m for m in msgs if t0 + 30 * M <= float(m["t_meas"]) < t0 + 60 * M]  # type: ignore[arg-type]
    assert len(block) == 360
    assert sum(bool(m["motion"]) for m in block) >= 0.95 * len(block)
    outside = [m for m in msgs if float(m["t_meas"]) < t0 + 29 * M]  # type: ignore[arg-type]
    assert not any(bool(m["motion"]) for m in outside)


def test_only_w1_is_named_and_end_event_exists() -> None:
    world = build_world(load_scenario("exercise_block"), 1, DEFAULT_START)
    assert [(e.phase, e.crew, e.label) for e in world.events] == [
        ("start", "W1", "W1 exercise block begins"),
        ("end", "W1", "W1 exercise block ends"),
    ]
