"""Scenario effect operations: each turns into an additive offset on one model target.

Targets are ``cabin.<x>`` (co2 in ppm, temp in C, rh, voc, cpm) or ``crew.<id>.<x>`` (hr, rmssd,
skin, spo2, act). An effect is active from its start until its end (``for``), or to the end of the
scenario when no ``for`` is given. Thresholds are referenced by path into the thresholds file and
converted to the target's unit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ccm_sim.scenario import ScenarioError
from ccm_sim.thresholds import Thresholds
from ccm_sim.units import mmhg_to_ppm

if TYPE_CHECKING:
    from ccm_sim.truth import Truth

CABIN_BASE = {
    "co2": "co2_base",
    "temp": "temp_base",
    "rh": "rh_base",
    "voc": "voc_base",
    "cpm": "cpm_base",
}
CREW_BASE = {"hr": "hr0", "rmssd": "rmssd0", "skin": "skin0", "spo2": "spo2_0", "act": "act_rest"}
CABIN_UNITS = {"co2": "ppm", "temp": "C", "rh": "%", "voc": "index", "cpm": "counts/min"}
CREW_UNITS = {"hr": "bpm", "rmssd": "ms", "skin": "C", "spo2": "%", "act": "g"}


class Baselines:
    """Noise-free baseline level of every target, taken from the parameter files."""

    def __init__(self, cabin: dict[str, float], crew: dict[str, dict[str, float]]) -> None:
        self._cabin = cabin
        self._crew = crew

    def base(self, target: str) -> float:
        parts = target.split(".")
        if parts[0] == "cabin" and len(parts) == 2 and parts[1] in CABIN_BASE:
            return self._cabin[CABIN_BASE[parts[1]]]
        if parts[0] == "crew" and len(parts) == 3 and parts[2] in CREW_BASE:
            params = self._crew.get(parts[1]) or self._crew["W1"]
            return params[CREW_BASE[parts[2]]]
        raise ScenarioError(f"unknown target {target!r}")


def unit_of(target: str) -> str:
    parts = target.split(".")
    if parts[0] == "cabin" and len(parts) == 2 and parts[1] in CABIN_UNITS:
        return CABIN_UNITS[parts[1]]
    if parts[0] == "crew" and len(parts) == 3 and parts[2] in CREW_UNITS:
        return CREW_UNITS[parts[2]]
    raise ScenarioError(f"unknown target {target!r}")


def threshold_in_unit(thresholds: Thresholds, path: str, unit: str) -> float:
    """Return the threshold at ``path`` expressed in ``unit`` (mmHg thresholds convert to ppm)."""
    leaf = thresholds.leaf(path)
    value = float(leaf["value"])
    have = str(leaf["unit"])
    if have == unit:
        return value
    if have == "mmHg" and unit == "ppm":
        return mmhg_to_ppm(value, thresholds.cabin_pressure_mmhg)
    raise ScenarioError(f"cannot express threshold {path!r} ({have}) in {unit}")


def resolve_value(spec: Any, unit: str, thresholds: Thresholds) -> float:
    """A number, or ``{threshold: path, factor: x}`` converted to ``unit``."""
    if isinstance(spec, dict):
        factor = float(spec.get("factor", 1.0))
        return threshold_in_unit(thresholds, spec["threshold"], unit) * factor
    return float(spec)


@dataclass
class Effect:
    """One concrete effect on one concrete target, with absolute start and end times."""

    op: str
    target: str
    start: float
    end: float | None
    args: dict[str, Any]
    base: float
    unit: str
    to_value: float = 0.0
    thr_value: float = 0.0
    peak_excess: float = 1.0
    extra: dict[str, Any] = field(default_factory=dict)

    def active(self, t: float) -> bool:
        return t >= self.start and (self.end is None or t < self.end)

    def offset(self, t: float, truth: Truth) -> float:
        if not self.active(t):
            return 0.0
        u = t - self.start
        a = self.args
        if self.op == "set":
            return float(a["value"]) - self.base
        if self.op == "step":
            return float(a["delta"])
        if self.op == "ramp":
            return (self.to_value - self.base) * min(1.0, u / float(a["over"]))
        if self.op == "drift_per_day":
            days = float(a["days"]) if "days" in a else u / 86400.0
            return float(a["delta"]) * min(u / 86400.0, days)
        if self.op == "exercise":
            return float(a["act"]) - self.base
        if self.op == "rate":
            return float(a["cpm"]) - self.base
        if self.op == "coupled":
            lag = float(a["start"].get("lag", 0.0))
            excess = max(0.0, truth.driver_level(a["driver"], t - lag) - self.thr_value)
            return float(a["gain_at_peak"]) * excess / self.peak_excess
        return 0.0  # silence has no offset; the publisher reads it from the truth
