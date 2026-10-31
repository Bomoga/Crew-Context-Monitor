from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
import yaml

from ccm_sim.physiology import (
    PARAMS_DIR,
    CrewPhysiology,
    ParamsError,
    Snapshot,
    load_physiology,
)

T0 = 1_760_000_000.0
DAY = 86400.0
PARAMS = load_physiology()


def run(
    crew: str = "W1",
    seed: int = 1,
    duration: float = DAY,
    cabin: Callable[[float], float] = lambda t: 22.0,
    offsets: Callable[[str, float], float] | None = None,
    params: dict[str, float] | None = None,
) -> list[Snapshot]:
    phys = CrewPhysiology(crew, params or PARAMS[crew], seed, T0, cabin, offsets)
    out: list[Snapshot] = []
    t = T0
    while t < T0 + duration:
        t += 5.0
        out.append(phys.advance_to(t))
    return out


def flat(crew: str = "W1") -> dict[str, float]:
    """Parameters with circadian terms off so paired runs differ only by the tested input."""
    return {**PARAMS[crew], "hr_circ_amp": 0.0, "act_diurnal_amp": 0.0, "skin_circ_amp": 0.0}


def test_params_have_sources_and_crew_variation() -> None:
    assert PARAMS["W1"]["hr0"] == 62
    assert PARAMS["W2"]["hr0"] == 66
    assert PARAMS["W3"]["hr0"] == 58
    raw = yaml.safe_load((PARAMS_DIR / "physiology.yaml").read_text(encoding="utf-8"))
    assert all(leaf["source"] for leaf in raw["defaults"].values())


def test_param_without_source_is_rejected(tmp_path: Path) -> None:
    raw = yaml.safe_load((PARAMS_DIR / "physiology.yaml").read_text(encoding="utf-8"))
    del raw["defaults"]["hr0"]["source"]
    bad = tmp_path / "physiology.yaml"
    bad.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ParamsError, match="hr0"):
        load_physiology(bad)


@pytest.mark.parametrize("crew", ["W1", "W2", "W3"])
def test_quiet_day_means_match_params(crew: str) -> None:
    snaps = run(crew)
    p = PARAMS[crew]
    assert abs(np.mean([s.hr_target for s in snaps]) - p["hr0"]) < 1.0
    assert abs(np.mean([s.rmssd_target for s in snaps]) - p["rmssd0"]) / p["rmssd0"] < 0.05
    assert abs(np.mean([s.spo2 for s in snaps]) - p["spo2_0"]) < 0.5
    assert abs(np.mean([s.skin_c for s in snaps]) - p["skin0"]) < 0.15
    assert 0.0 < np.mean([s.act for s in snaps]) < 0.12
    assert not any(s.motion for s in snaps)
    assert all(90 <= s.spo2 <= 100 for s in snaps)


def test_cabin_temperature_step_raises_hr_by_beta2() -> None:
    p = flat()
    step_t = T0 + 4 * 3600.0
    base = run(params=p, duration=12 * 3600.0)
    hot = run(params=p, duration=12 * 3600.0, cabin=lambda t: 25.0 if t >= step_t else 22.0)
    late = slice(int(8 * 3600 / 5), None)  # four hours after the step
    diff = np.mean([h.hr_target - b.hr_target for h, b in zip(hot[late], base[late], strict=True)])
    assert abs(diff - p["beta2"] * 3.0) < 1.0


def test_rest_to_exercise_raises_hr_by_beta1_times_delta_act() -> None:
    p = flat()
    start = T0 + 2 * 3600.0
    delta = p["act_exercise"] - p["act_rest"]

    def ex(target: str, t: float) -> float:
        return delta if target == "act" and t >= start else 0.0

    base = run(params=p, duration=4 * 3600.0)
    hard = run(params=p, duration=4 * 3600.0, offsets=ex)
    late = slice(int(3 * 3600 / 5), None)
    diff = np.mean([h.hr_target - b.hr_target for h, b in zip(hard[late], base[late], strict=True)])
    assert abs(diff - p["beta1"] * delta) < 3.0
    assert all(s.motion for s in hard[late])


def test_skin_reaches_63_percent_in_20_minutes() -> None:
    p = flat()
    step_t = T0 + 3600.0
    base = run(params=p, duration=8 * 3600.0)
    hot = run(params=p, duration=8 * 3600.0, cabin=lambda t: 25.0 if t >= step_t else 22.0)
    diff = np.array([h.skin_c - b.skin_c for h, b in zip(hot, base, strict=True)])
    final = diff[-1]
    assert final == pytest.approx(p["skin_cabin_gain"] * 3.0, abs=0.02)
    idx = int(np.argmax(diff >= 0.632 * final))
    t_cross = (idx + 1) * 5.0 - 3600.0
    assert abs(t_cross - 1200.0) <= 180.0


def test_same_seed_repeats_and_crew_streams_are_independent() -> None:
    a = [s.hr_target for s in run("W1", seed=3, duration=3600.0)]
    b = [s.hr_target for s in run("W1", seed=3, duration=3600.0)]
    assert a == b
    c = [s.hr_target for s in run("W2", seed=3, duration=3600.0)]
    assert a != c


def test_battery_discharges_slowly() -> None:
    snaps = run(duration=2 * DAY)
    assert snaps[0].batt == pytest.approx(4.15, abs=0.001)
    assert 3.85 < snaps[-1].batt < 4.0
