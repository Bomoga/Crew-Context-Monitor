"""Truth channels: the noise-free levels and offsets a scenario applies, per target.

``Truth.offset(target, t)`` is what the models add to their baselines. ``Truth.level`` is the
baseline plus that offset, in the channel's unit. ``series`` samples a channel every minute; the
mock API and the expectation checks read these instead of the noisy generated data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

from ccm_sim.effects import (
    Baselines,
    Effect,
    resolve_value,
    threshold_in_unit,
    unit_of,
)
from ccm_sim.scenario import EffectSpec, Scenario, ScenarioError
from ccm_sim.thresholds import Thresholds

GRID_STEP = 60.0
_CONDITION = re.compile(r"^\s*([a-z0-9_.*]+)\s*(>=|<=|>|<)\s*(\S+)\s*$")


@dataclass(frozen=True)
class Silence:
    """A node that goes quiet; the publisher implements it (T3.9)."""

    node: str
    t_start: float
    t_end: float
    buffer: bool


class Truth:
    """All effects of one scenario run, expanded to concrete targets."""

    def __init__(
        self,
        scenario: Scenario,
        crew: list[str],
        t0: float,
        duration: float,
        thresholds: Thresholds,
        baselines: Baselines,
    ) -> None:
        self.t0 = t0
        self.duration = duration
        # the peak a coupled effect scales to is a property of the scenario, not of a short run
        self._peak_span = max(duration, scenario.duration)
        self.crew = crew
        self.thresholds = thresholds
        self.baselines = baselines
        self.effects: list[Effect] = []
        self.silences: list[Silence] = []
        self._by_target: dict[str, list[Effect]] = {}
        self._plain: dict[str, list[Effect]] = {}
        for event in scenario.events:
            start = t0 + event.at
            for spec in event.effects:
                self._add(spec, start)
        self._finish_coupled()

    # -- building -----------------------------------------------------------------------------
    def _targets(self, spec: EffectSpec) -> list[str]:
        assert spec.target is not None
        parts = spec.target.split(".")
        if parts[0] == "crew" and parts[1] == "*":
            return [f"crew.{c}.{parts[2]}" for c in self.crew]
        if parts[0] == "crew" and parts[1] not in self.crew:
            return []
        return [spec.target]

    def _add(self, spec: EffectSpec, start: float) -> None:
        args = dict(spec.args)
        end = start + args["for"] if "for" in args else None
        if spec.op == "silence":
            self.silences.append(
                Silence(args["node"], start, start + args["for"], bool(args.get("buffer", False)))
            )
            return
        for target in self._targets(spec):
            unit = unit_of(target)
            base = self.baselines.base(target)
            effect = Effect(spec.op, target, start, end, args, base, unit)
            if spec.op == "ramp" and "to" in args:
                effect.to_value = resolve_value(args["to"], unit, self.thresholds)
            if spec.op == "coupled":
                effect.thr_value = threshold_in_unit(
                    self.thresholds, args["start"]["above_threshold"], unit_of(args["driver"])
                )
            self.effects.append(effect)
            self._by_target.setdefault(target, []).append(effect)
            if spec.op != "coupled":
                self._plain.setdefault(target, []).append(effect)

    def _finish_coupled(self) -> None:
        for effect in self.effects:
            if effect.op != "coupled":
                continue
            driver = effect.args["driver"]
            peak = max(
                (
                    self.driver_level(driver, self.t0 + k * GRID_STEP) - effect.thr_value
                    for k in range(int(self._peak_span / GRID_STEP) + 1)
                ),
                default=0.0,
            )
            if peak <= 0:
                raise ScenarioError(
                    f"driver {driver!r} never rises above "
                    f"{effect.args['start']['above_threshold']!r}; check thresholds.yaml "
                    "and the scenario ramp (D6)"
                )
            effect.peak_excess = peak

    # -- queries ------------------------------------------------------------------------------
    def driver_level(self, channel: str, t: float) -> float:
        """Baseline plus non-coupled effects: what a coupled effect follows."""
        total = self.baselines.base(channel)
        for effect in self._plain.get(channel, ()):
            total += effect.offset(t, self)
        return total

    def offset(self, target: str, t: float) -> float:
        effects = self._by_target.get(target)
        if not effects:
            return 0.0
        return sum(e.offset(t, self) for e in effects)

    def level(self, channel: str, t: float) -> float:
        return self.baselines.base(channel) + self.offset(channel, t)

    def times(self, step: float = GRID_STEP) -> np.ndarray:
        return self.t0 + step * np.arange(int(self.duration / step) + 1)

    def series(self, channel: str, step: float = GRID_STEP) -> np.ndarray:
        """Noise-free level of ``channel`` every ``step`` seconds from the start."""
        return np.array([self.level(channel, float(t)) for t in self.times(step)])

    def offset_series(self, target: str, step: float = GRID_STEP) -> np.ndarray:
        return np.array([self.offset(target, float(t)) for t in self.times(step)])

    # -- conditions ---------------------------------------------------------------------------
    def condition_holds(self, condition: str, t: float) -> bool:
        match = _CONDITION.match(condition)
        if not match:
            raise ScenarioError(f"cannot parse condition {condition!r}")
        channel, op, rhs = match.groups()
        value = self.level(channel, t)
        try:
            limit = float(rhs)
        except ValueError:
            limit = threshold_in_unit(self.thresholds, rhs, unit_of(channel))
        return {
            ">=": value >= limit,
            ">": value > limit,
            "<=": value <= limit,
            "<": value < limit,
        }[op]

    def first_time(self, condition: str) -> float | None:
        """First grid time (minute) at which ``condition`` holds, or None."""
        for t in self.times():
            if self.condition_holds(condition, float(t)):
                return float(t)
        return None
