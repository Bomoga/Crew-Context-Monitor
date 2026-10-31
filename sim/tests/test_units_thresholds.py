import math
from pathlib import Path

import pytest
import yaml

from ccm_sim.thresholds import ThresholdsError, default_path, load_thresholds
from ccm_sim.units import mmhg_to_ppm, ppm_to_mmhg


def test_five_thousand_ppm_is_3_8_mmhg() -> None:
    assert math.isclose(ppm_to_mmhg(5000), 3.8, abs_tol=1e-9)


@pytest.mark.parametrize("ppm", [0.0, 400.0, 812.0, 5130.0, 40000.0])
def test_round_trip(ppm: float) -> None:
    assert math.isclose(mmhg_to_ppm(ppm_to_mmhg(ppm)), ppm, abs_tol=1e-9)


def test_pressure_is_configurable() -> None:
    assert math.isclose(ppm_to_mmhg(1000, pressure_mmhg=500.0), 0.5, abs_tol=1e-12)


def test_loader_reads_provisional_values() -> None:
    t = load_thresholds()
    assert t.status == "provisional"
    assert t.co2_mmhg("yellow") == 2.5
    assert t.co2_mmhg("red") == 3.0
    assert math.isclose(t.co2_ppm("red"), 3.0 / 760e-6)
    assert t.value("thermal.cabin_temp_c.hi") == 27
    assert t.value("radiation.poisson.k_sigma") == 4


def test_loader_rejects_missing_key(tmp_path: Path) -> None:
    data = yaml.safe_load(default_path().read_text(encoding="utf-8"))
    del data["air"]["co2"]["red"]
    bad = tmp_path / "thresholds.yaml"
    bad.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ThresholdsError, match="air.co2.red"):
        load_thresholds(bad)


def test_loader_rejects_leaf_without_source(tmp_path: Path) -> None:
    data = yaml.safe_load(default_path().read_text(encoding="utf-8"))
    del data["air"]["co2"]["yellow"]["source"]
    bad = tmp_path / "thresholds.yaml"
    bad.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ThresholdsError, match="source"):
        load_thresholds(bad)


def test_every_leaf_is_provisional() -> None:
    def walk(node: object) -> list[dict[str, object]]:
        if isinstance(node, dict):
            if "value" in node:
                return [node]
            return [leaf for v in node.values() for leaf in walk(v)]
        return []

    leaves = walk({k: v for k, v in load_thresholds().data.items() if k != "status"})
    assert leaves
    assert all(leaf["status"] == "provisional" and leaf["source"] for leaf in leaves)
