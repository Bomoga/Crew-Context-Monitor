"""Crew physiology model.

HR(t) = hr0 + circadian + beta1 * (act_f - act_ref) + beta2 * (T_cabin - 22) + scenario + noise.
The state advances on a fixed grid (``DT`` seconds) and is held between grid points, which is fine
for slow physiology and keeps week-long runs cheap.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

from ccm_sim.params import PARAMS_DIR, flatten
from ccm_sim.rng import stream

DT = 5.0
CABIN_T_REF = 22.0
SEC_PER_DAY = 86400.0
_CHUNK = 2048

OffsetFn = Callable[[str, float], float]


def load_physiology(path: Path | None = None) -> dict[str, dict[str, float]]:
    """Return ``{crew_id: params}`` with the defaults merged under each crew override."""
    raw = yaml.safe_load((path or PARAMS_DIR / "physiology.yaml").read_text(encoding="utf-8"))
    defaults = flatten(raw["defaults"], "defaults")
    crews: dict[str, dict[str, float]] = {}
    for crew_id, override in raw["crew"].items():
        crews[crew_id] = {**defaults, **flatten(override or {}, f"crew.{crew_id}")}
    return crews


def _hour_utc(t: float) -> float:
    return (t % SEC_PER_DAY) / 3600.0


@dataclass(frozen=True)
class Snapshot:
    """Physiology at one grid time."""

    t: float
    hr_target: float
    hr_model: float  # the model's explanation of HR: no scenario offsets, no noise
    rmssd_target: float
    spo2: int
    skin_c: float
    act: float
    motion: bool
    batt: float
    cabin_temp_c: float


class CrewPhysiology:
    """One crew member's physiology, advanced causally in simulated time."""

    def __init__(
        self,
        crew: str,
        params: dict[str, float],
        seed: int,
        t0: float,
        cabin_temp_fn: Callable[[float], float],
        offset_fn: OffsetFn | None = None,
    ) -> None:
        self.crew = crew
        self.p = params
        self._t0 = t0
        self._cabin_temp_fn = cabin_temp_fn
        self._offset_fn = offset_fn or (lambda target, t: 0.0)
        self._rng = stream(seed, f"crew.{crew}.physiology")
        self._z = self._rng.standard_normal((_CHUNK, 4))
        self._zi = 0
        self._last_z = np.zeros(4)
        self._phi_hr = math.exp(-DT / params["hr_noise_tau_s"])
        self._phi_rm = math.exp(-DT / params["rmssd_noise_tau_s"])
        self._n_hr = 0.0
        self._n_rm = 0.0
        self._t = t0
        self._act_f = params["act_rest"]
        cabin = cabin_temp_fn(t0)
        self._skin = self._skin_target(t0, cabin)
        self._snap = self._compute(t0, params["act_rest"], cabin)

    # -- model pieces -------------------------------------------------------------------------
    def circadian_hr(self, t: float) -> float:
        return self.p["hr_circ_amp"] * math.cos(2 * math.pi * (_hour_utc(t) - 16.0) / 24.0)

    def _circ_rmssd(self, t: float) -> float:
        return self.p["rmssd_circ_frac"] * math.cos(2 * math.pi * (_hour_utc(t) - 4.0) / 24.0)

    def _skin_target(self, t: float, cabin: float) -> float:
        p = self.p
        circ = p["skin_circ_amp"] * math.cos(2 * math.pi * (_hour_utc(t) - 16.0) / 24.0)
        return (
            p["skin0"]
            + p["skin_cabin_gain"] * (cabin - CABIN_T_REF)
            + circ
            + self._offset_fn("skin", t)
        )

    def predict_hr(self, t: float, act_f: float, cabin_temp_c: float) -> float:
        """The model's explanation of HR: everything except scenario offsets and noise."""
        p = self.p
        return (
            p["hr0"]
            + self.circadian_hr(t)
            + p["beta1"] * (act_f - p["act_ref"])
            + p["beta2"] * (cabin_temp_c - CABIN_T_REF)
        )

    def _compute(self, t: float, act: float, cabin: float) -> Snapshot:
        p = self.p
        hr_model = self.predict_hr(t, self._act_f, cabin)
        hr = hr_model + self._offset_fn("hr", t) + self._n_hr
        rm = (
            p["rmssd0"]
            * (1.0 + self._circ_rmssd(t))
            * math.exp(-p["rmssd_act_gamma"] * (self._act_f - p["act_ref"]))
            + self._offset_fn("rmssd", t)
            + self._n_rm
        )
        motion = act > p["act_motion_threshold"]
        sd = p["spo2_motion_noise_sd"] if motion else p["spo2_noise_sd"]
        z_spo2 = float(self._last_z[3])
        spo2 = int(
            round(min(100.0, max(90.0, p["spo2_0"] + self._offset_fn("spo2", t) + sd * z_spo2)))
        )
        batt = max(3.1, p["batt_v0"] - p["batt_v_per_day"] * (t - self._t0) / SEC_PER_DAY)
        return Snapshot(
            t=t,
            hr_target=hr,
            hr_model=hr_model,
            rmssd_target=max(p["rmssd_min"], rm),
            spo2=spo2,
            skin_c=self._skin,
            act=act,
            motion=motion,
            batt=batt,
            cabin_temp_c=cabin,
        )

    # -- time stepping ------------------------------------------------------------------------
    def _step(self) -> None:
        p = self.p
        if self._zi >= _CHUNK:
            self._z = self._rng.standard_normal((_CHUNK, 4))
            self._zi = 0
        z = self._z[self._zi]
        self._zi += 1
        self._last_z = z
        t = self._t + DT
        self._n_hr = self._phi_hr * self._n_hr + p["hr_noise_sd"] * math.sqrt(
            1 - self._phi_hr**2
        ) * float(z[0])
        self._n_rm = self._phi_rm * self._n_rm + p["rmssd_noise_sd"] * math.sqrt(
            1 - self._phi_rm**2
        ) * float(z[1])
        diurnal = p["act_diurnal_amp"] * math.sin(2 * math.pi * (_hour_utc(t) - 8.0) / 24.0)
        act = max(
            0.0,
            p["act_rest"]
            + diurnal
            + p["act_rest_noise_sd"] * float(z[2])
            + self._offset_fn("act", t),
        )
        tau = p["tau_act_rise_s"] if act > self._act_f else p["tau_act_recover_s"]
        self._act_f += (act - self._act_f) * (1.0 - math.exp(-DT / tau))
        cabin = self._cabin_temp_fn(t)
        self._skin += (self._skin_target(t, cabin) - self._skin) * (
            1.0 - math.exp(-DT / p["skin_tau_s"])
        )
        self._t = t
        self._snap = self._compute(t, act, cabin)

    def advance_to(self, t: float) -> Snapshot:
        """Advance to the last grid time at or before ``t`` and return the snapshot there."""
        while self._t + DT <= t:
            self._step()
        return self._snap

    def hr_fn(self, t: float) -> float:
        return self.advance_to(t).hr_target

    def rmssd_fn(self, t: float) -> float:
        return self.advance_to(t).rmssd_target

    @property
    def act_filtered(self) -> float:
        return self._act_f
