"""Beat-level inter-beat interval generator (PLAN Appendix C).

Per beat n: RR_n = 60000 / HR(t_n) + x_n + r_n, where x_n is AR(1) and r_n a small respiratory
sinus term. ``sigma_eps = RMSSD_target * sqrt((1 + phi) / 2)`` makes the stationary RMSSD of the
AR(1) term equal the target.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np

RR_MIN_MS = 300
RR_MAX_MS = 2000
_CHUNK = 4096


class BeatGenerator:
    """Incremental beat source. ``advance_to(t_end)`` returns the beats that end before ``t_end``.

    Each returned pair is ``(beat_time_s, rr_ms)``: the time of the beat that closes an interval
    and the integer length of that interval in milliseconds.
    """

    def __init__(
        self,
        rng: np.random.Generator,
        hr_fn: Callable[[float], float],
        rmssd_fn: Callable[[float], float],
        t0: float,
        phi: float = 0.3,
        resp_amp_ms: float = 3.0,
        resp_period_s: float = 4.0,
        calibration: float = 1.0,
    ) -> None:
        self._rng = rng
        self._hr_fn = hr_fn
        self._rmssd_fn = rmssd_fn
        self._phi = phi
        self._resp_amp = resp_amp_ms
        self._resp_period = resp_period_s
        self._calibration = calibration
        self._buf = rng.standard_normal(_CHUNK)
        self._i = 0
        sigma_x = self._sigma_eps(t0) / math.sqrt(1.0 - phi * phi)
        self._x = sigma_x * self._normal()
        self._t_prev = t0
        self._pending: tuple[float, int] | None = None

    def _normal(self) -> float:
        if self._i >= _CHUNK:
            self._buf = self._rng.standard_normal(_CHUNK)
            self._i = 0
        z = float(self._buf[self._i])
        self._i += 1
        return z

    def _sigma_eps(self, t: float) -> float:
        rmssd = self._rmssd_fn(t) * self._calibration
        return rmssd * math.sqrt((1.0 + self._phi) / 2.0)

    def _next_beat(self) -> tuple[float, int]:
        t = self._t_prev
        self._x = self._phi * self._x + self._sigma_eps(t) * self._normal()
        resp = self._resp_amp * math.sin(2.0 * math.pi * t / self._resp_period)
        rr = 60000.0 / self._hr_fn(t) + self._x + resp
        rr_ms = int(round(min(max(rr, RR_MIN_MS), RR_MAX_MS)))
        self._t_prev = t + rr_ms / 1000.0
        return self._t_prev, rr_ms

    def advance_to(self, t_end: float) -> list[tuple[float, int]]:
        """Return all beats with time strictly before ``t_end`` that have not been returned yet."""
        out: list[tuple[float, int]] = []
        while True:
            if self._pending is None:
                self._pending = self._next_beat()
            if self._pending[0] >= t_end:
                return out
            out.append(self._pending)
            self._pending = None


def generate_beats(
    rng: np.random.Generator,
    hr_fn: Callable[[float], float],
    rmssd_fn: Callable[[float], float],
    t0: float,
    t_end: float,
    **kwargs: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate beats in ``[t0, t_end)``; return ``(beat_times_s, rr_ms)`` as arrays."""
    beats = BeatGenerator(rng, hr_fn, rmssd_fn, t0, **kwargs).advance_to(t_end)
    times = np.array([b[0] for b in beats], dtype=float)
    rr = np.array([b[1] for b in beats], dtype=np.int64)
    return times, rr


def rmssd(rr_ms: np.ndarray) -> float:
    """RMSSD = sqrt(1/(N-1) * sum((RR[i+1] - RR[i])^2)) as in Appendix C."""
    d = np.diff(rr_ms.astype(float))
    return float(math.sqrt(float(np.sum(d * d)) / len(d)))
