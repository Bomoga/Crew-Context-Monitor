import json
from collections.abc import Callable

import numpy as np
import pytest

from ccm_sim import contracts
from ccm_sim.cabin import CABIN_DT, CabinModel, CabinSnapshot, load_cabin_params

T0 = 1_760_000_000.0
SEEDS = [1, 2, 3, 4, 5]
PARAMS = load_cabin_params()


def run(
    seed: int, hours: float = 6.0, offsets: Callable[[str, float], float] | None = None
) -> list[CabinSnapshot]:
    model = CabinModel(PARAMS, seed, T0, offsets)
    return [model.advance_to(T0 + CABIN_DT * k) for k in range(1, int(hours * 360) + 1)]


@pytest.mark.parametrize("seed", SEEDS)
def test_radiation_counts_are_poisson_at_18_cpm(seed: int) -> None:
    snaps = run(seed)
    c10 = np.array([s.c10s for s in snaps])
    assert abs(np.mean([s.cpm for s in snaps]) - 18.0) < 1.0
    assert 0.8 < float(np.var(c10) / np.mean(c10)) < 1.2
    assert float(np.mean(c10)) == pytest.approx(3.0, abs=0.2)


@pytest.mark.parametrize("seed", SEEDS)
def test_fields_stay_inside_schema_ranges(seed: int) -> None:
    schema = json.loads(
        (contracts.contracts_dir() / "mqtt" / "cabin_telemetry.schema.json").read_text("utf-8")
    )["properties"]
    for s in run(seed):
        assert schema["co2"]["minimum"] <= s.co2 <= schema["co2"]["maximum"]
        assert schema["temp_c"]["minimum"] <= s.temp_c <= schema["temp_c"]["maximum"]
        assert schema["rh"]["minimum"] <= s.rh <= schema["rh"]["maximum"]
        assert schema["voc"]["minimum"] <= s.voc <= schema["voc"]["maximum"]
        assert 0 <= s.pm1 <= s.pm25 <= s.pm10
        assert s.cpm >= 0 and s.c10s >= 0


def test_baseline_means_match_params() -> None:
    snaps = run(1, hours=24.0)
    assert abs(np.mean([s.co2 for s in snaps]) - PARAMS["co2_base"]) < 20
    assert abs(np.mean([s.temp_c for s in snaps]) - PARAMS["temp_base"]) < 0.1
    assert abs(np.mean([s.rh for s in snaps]) - PARAMS["rh_base"]) < 0.5
    assert abs(np.mean([s.voc for s in snaps]) - PARAMS["voc_base"]) < 3


def test_offsets_and_rate_change_apply() -> None:
    def off(target: str, t: float) -> float:
        return {"co2": 500.0, "temp": 3.0, "cpm": 222.0}.get(target, 0.0)

    snaps = run(2, hours=1.0, offsets=off)
    assert abs(np.mean([s.co2 for s in snaps]) - 1300) < 30
    assert abs(np.mean([s.temp_c for s in snaps]) - 25.0) < 0.3
    assert abs(np.mean([s.cpm for s in snaps][10:]) - 240.0) < 8


def test_same_seed_repeats() -> None:
    assert run(7, hours=1.0) == run(7, hours=1.0)
