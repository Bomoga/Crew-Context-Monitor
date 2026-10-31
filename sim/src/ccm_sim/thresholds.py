"""Loader for ``contracts/thresholds.yaml``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ccm_sim import contracts
from ccm_sim.units import mmhg_to_ppm

REQUIRED_PATHS = (
    "cabin.pressure_mmhg",
    "air.co2.yellow",
    "air.co2.red",
    "air.voc_index.yellow",
    "thermal.cabin_temp_c.lo",
    "thermal.cabin_temp_c.hi",
    "thermal.skin_residual_c.yellow",
    "thermal.skin_residual_c.red",
    "thermal.skin_residual_c.duration_min",
    "radiation.poisson.window_s",
    "radiation.poisson.k_sigma",
    "radiation.poisson.yellow_windows",
    "radiation.poisson.red_windows",
)
LEAF_KEYS = ("value", "unit", "source", "status")


class ThresholdsError(ValueError):
    """Raised when the thresholds file is missing a key or has a malformed leaf."""


@dataclass(frozen=True)
class Thresholds:
    data: dict[str, Any]

    @property
    def status(self) -> str:
        return str(self.data["status"])

    def leaf(self, path: str) -> dict[str, Any]:
        node: Any = self.data
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                raise ThresholdsError(f"thresholds file has no entry {path!r}")
            node = node[part]
        if not isinstance(node, dict) or "value" not in node:
            raise ThresholdsError(f"thresholds entry {path!r} is not a value leaf")
        return node

    def value(self, path: str) -> float:
        return float(self.leaf(path)["value"])

    @property
    def cabin_pressure_mmhg(self) -> float:
        return self.value("cabin.pressure_mmhg")

    def co2_mmhg(self, level: str) -> float:
        return self.value(f"air.co2.{level}")

    def co2_ppm(self, level: str) -> float:
        return mmhg_to_ppm(self.co2_mmhg(level), self.cabin_pressure_mmhg)


def default_path() -> Path:
    return contracts.contracts_dir() / "thresholds.yaml"


def load_thresholds(path: Path | None = None) -> Thresholds:
    """Load and check a thresholds file (default: ``contracts/thresholds.yaml``)."""
    raw = yaml.safe_load((path or default_path()).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "status" not in raw:
        raise ThresholdsError("thresholds file needs a top-level 'status' key")
    result = Thresholds(raw)
    for req in REQUIRED_PATHS:
        leaf = result.leaf(req)
        missing = [k for k in LEAF_KEYS if k not in leaf]
        if missing:
            raise ThresholdsError(f"thresholds entry {req!r} is missing {missing}")
    return result
