import numpy as np
import pytest

from ccm_sim.beats import BeatGenerator, generate_beats, rmssd
from ccm_sim.rng import stream

SEEDS = [1, 2, 3, 4, 5]
HOUR = 3600.0
T0 = 1_760_000_000.0


def window_rmssd(times: np.ndarray, rr: np.ndarray, lo: float, hi: float) -> float:
    m = (times >= lo) & (times < hi)
    return rmssd(rr[m])


@pytest.mark.parametrize("seed", SEEDS)
def test_quiet_hour_matches_targets(seed: int) -> None:
    times, rr = generate_beats(
        stream(seed, "crew.W1.ibi"), lambda t: 62.0, lambda t: 45.0, T0, T0 + HOUR
    )
    mean_hr = 60000.0 / float(np.mean(rr))
    assert abs(mean_hr - 62.0) < 1.0
    medians = [window_rmssd(times, rr, T0 + k * 300, T0 + (k + 1) * 300) for k in range(12)]
    assert abs(float(np.median(medians)) - 45.0) / 45.0 < 0.15


@pytest.mark.parametrize("seed", SEEDS)
def test_beats_are_ordered_and_in_range(seed: int) -> None:
    times, rr = generate_beats(
        stream(seed, "crew.W1.ibi"), lambda t: 62.0, lambda t: 45.0, T0, T0 + HOUR
    )
    assert np.all(np.diff(times) > 0)
    assert rr.min() >= 300
    assert rr.max() <= 2000


@pytest.mark.parametrize("seed", SEEDS)
def test_rmssd_step_down_is_tracked_within_ten_minutes(seed: int) -> None:
    t_change = T0 + 1800.0
    rmssd_fn = lambda t: 45.0 if t < t_change else 30.0  # noqa: E731
    times, rr = generate_beats(stream(seed, "crew.W1.ibi"), lambda t: 62.0, rmssd_fn, T0, T0 + HOUR)
    ends = [t_change + 300.0 + 30.0 * k for k in range(0, 11)]  # window ends up to +10 min
    values = [window_rmssd(times, rr, e - 300.0, e) for e in ends]
    assert any(abs(v - 30.0) / 30.0 < 0.15 for v in values)
    assert abs(values[-1] - 30.0) / 30.0 < 0.15


def test_incremental_matches_one_shot() -> None:
    hr = lambda t: 62.0  # noqa: E731
    rm = lambda t: 45.0  # noqa: E731
    one_t, one_rr = generate_beats(stream(9, "x"), hr, rm, T0, T0 + 600.0)
    gen = BeatGenerator(stream(9, "x"), hr, rm, T0)
    got: list[tuple[float, int]] = []
    for k in range(1, 121):
        got += gen.advance_to(T0 + 5.0 * k)
    assert [b[1] for b in got] == one_rr.tolist()
    assert np.allclose([b[0] for b in got], one_t)


def test_hr_target_tracks_a_change() -> None:
    hr = lambda t: 60.0 if t < T0 + 1800.0 else 90.0  # noqa: E731
    times, rr = generate_beats(stream(3, "hr"), hr, lambda t: 45.0, T0, T0 + HOUR)
    late = rr[times > T0 + 2400.0]
    assert abs(60000.0 / float(np.mean(late)) - 90.0) < 1.5
