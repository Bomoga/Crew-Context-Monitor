"""Cabin environment and radiation counts.

The state advances on a 10 s grid, the cabin message period. Scenario effects arrive as additive
offsets through ``offset_fn(target, t)`` for the targets ``co2`` (ppm), ``temp`` (C), ``rh``,
``voc`` and ``cpm`` (Geiger counts per minute).
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ccm_sim.params import PARAMS_DIR, load_block
from ccm_sim.rng import stream

CABIN_DT = 10.0
SEC_PER_DAY = 86400.0
_CHUNK = 2048

OffsetFn = Callable[[str, float], float]


def load_cabin_params(path: Path | None = None) -> dict[str, float]:
    return load_block(path or PARAMS_DIR / "cabin.yaml")


@dataclass(frozen=True)
class CabinSnapshot:
    t: float
    co2: int
    temp_c: float
    rh: float
    voc: int
    pm1: int
    pm25: int
    pm10: int
    cpm: int
    c10s: int


def _hour_utc(t: float) -> float:
    return (t % SEC_PER_DAY) / 3600.0


class CabinModel:
    """Cabin node C1's environment, advanced causally in simulated time."""

    def __init__(
        self,
        params: dict[str, float],
        seed: int,
        t0: float,
        offset_fn: OffsetFn | None = None,
        node_id: str = "C1",
    ) -> None:
        self.p = params
        self._offset_fn = offset_fn or (lambda target, t: 0.0)
        self._rng = stream(seed, f"cabin.{node_id}")
        self._z = self._rng.standard_normal((_CHUNK, 4))
        self._zi = 0
        self._phi = {
            "co2": math.exp(-CABIN_DT / params["co2_noise_tau_s"]),
            "temp": math.exp(-CABIN_DT / params["temp_noise_tau_s"]),
            "rh": math.exp(-CABIN_DT / params["rh_noise_tau_s"]),
            "voc": math.exp(-CABIN_DT / params["voc_noise_tau_s"]),
        }
        self._noise = {"co2": 0.0, "temp": 0.0, "rh": 0.0, "voc": 0.0}
        self._counts: deque[int] = deque(
            (int(self._rng.poisson(params["cpm_base"] / 6.0)) for _ in range(5)), maxlen=6
        )
        self._t = t0
        self._snap = self._compute(t0, int(self._rng.poisson(params["cpm_base"] / 6.0)))

    def _sd(self, name: str) -> float:
        return self.p[f"{name}_noise_sd"] * math.sqrt(1.0 - self._phi[name] ** 2)

    def _compute(self, t: float, c10s: int) -> CabinSnapshot:
        p = self.p
        off = self._offset_fn
        hour = _hour_utc(t)
        co2 = (
            p["co2_base"]
            + p["co2_diurnal_amp"] * math.cos(2 * math.pi * (hour - 14.0) / 24.0)
            + self._noise["co2"]
            + off("co2", t)
        )
        temp = (
            p["temp_base"]
            + p["temp_diurnal_amp"] * math.cos(2 * math.pi * (hour - 15.0) / 24.0)
            + self._noise["temp"]
            + off("temp", t)
        )
        rh = p["rh_base"] + self._noise["rh"] + off("rh", t)
        voc = p["voc_base"] + self._noise["voc"] + off("voc", t)
        pms = sorted(int(self._rng.poisson(p[f"{k}_base"])) for k in ("pm1", "pm25", "pm10"))
        self._counts.append(c10s)
        return CabinSnapshot(
            t=t,
            co2=int(round(min(40000.0, max(0.0, co2)))),
            temp_c=round(temp, 1),
            rh=round(min(100.0, max(0.0, rh)), 1),
            voc=int(round(min(500.0, max(0.0, voc)))),
            pm1=pms[0],
            pm25=pms[1],
            pm10=pms[2],
            cpm=sum(self._counts),
            c10s=c10s,
        )

    def _step(self) -> None:
        if self._zi >= _CHUNK:
            self._z = self._rng.standard_normal((_CHUNK, 4))
            self._zi = 0
        z = self._z[self._zi]
        self._zi += 1
        for i, name in enumerate(("co2", "temp", "rh", "voc")):
            self._noise[name] = self._phi[name] * self._noise[name] + self._sd(name) * float(z[i])
        t = self._t + CABIN_DT
        rate_cpm = max(0.0, self.p["cpm_base"] + self._offset_fn("cpm", t))
        self._t = t
        self._snap = self._compute(t, int(self._rng.poisson(rate_cpm / 6.0)))

    def advance_to(self, t: float) -> CabinSnapshot:
        """Advance to the last grid time at or before ``t`` and return the snapshot there."""
        while self._t + CABIN_DT <= t:
            self._step()
        return self._snap

    def temp_fn(self, t: float) -> float:
        return self.advance_to(t).temp_c
