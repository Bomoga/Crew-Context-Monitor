from __future__ import annotations

import math

import pytest

from ccm_sim.engine import build_world, run_world
from ccm_sim.messages import CABIN_TOPIC
from ccm_sim.scenario import load_scenario
from ccm_sim.sinks import MemorySink
from ccm_sim.thresholds import load_thresholds
from ccm_sim.timeutil import DEFAULT_START

SEEDS = [1, 2, 3, 4, 5]
WINDOW = 600.0
BASELINE_CPM = 18.0


def window_counts(seed: int) -> tuple[list[int], int, int]:
    """10-minute tumbling window counts, plus the first and last window index inside the step."""
    world = build_world(load_scenario("solar_particle_event"), seed, DEFAULT_START)
    sink = MemorySink()
    run_world(world, sink)
    n_windows = int(world.duration // WINDOW)
    counts = [0] * n_windows
    for r in sink.records:
        if r.topic == CABIN_TOPIC:
            k = int((r.payload["t_meas"] - DEFAULT_START - 1e-6) // WINDOW)
            if 0 <= k < n_windows:
                counts[k] += r.payload["c10s"]
    start = int(3600 // WINDOW)
    return counts, start, start + int(40 * 60 // WINDOW) - 1


def test_thresholds_match_the_plan_formula() -> None:
    t = load_thresholds()
    lam = BASELINE_CPM * WINDOW / 60.0
    assert t.value("radiation.poisson.window_s") == WINDOW
    assert lam + t.value("radiation.poisson.k_sigma") * math.sqrt(lam) == pytest.approx(
        233.67, abs=0.01
    )


def test_every_window_inside_the_step_exceeds_and_quiet_windows_do_not() -> None:
    t = load_thresholds()
    lam = BASELINE_CPM * WINDOW / 60.0
    limit = lam + t.value("radiation.poisson.k_sigma") * math.sqrt(lam)
    quiet_exceedances = 0
    for seed in SEEDS:
        counts, first, last = window_counts(seed)
        assert last - first + 1 == 4
        for k, n in enumerate(counts):
            if first <= k <= last:
                assert n > limit, (seed, k, n)
            elif n > limit:
                quiet_exceedances += 1
    assert quiet_exceedances <= 1


def test_event_start_and_end_are_published() -> None:
    world = build_world(load_scenario("solar_particle_event"), 1, DEFAULT_START)
    assert [(e.label, e.phase, e.t - DEFAULT_START) for e in world.events] == [
        ("Solar particle event begins", "start", 3600.0),
        ("Solar particle event ends", "end", 3600.0 + 2400.0),
    ]
