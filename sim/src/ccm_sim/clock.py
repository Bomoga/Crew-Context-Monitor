"""Simulation clock with a speed multiplier and an injectable real-time source."""

from __future__ import annotations

import time
from collections.abc import Callable


class SimClock:
    """Maps real elapsed time to simulated unix seconds.

    ``speed`` is a multiplier (60 means one real second is 60 simulated seconds) or ``"max"``.
    At ``"max"`` the clock never sleeps: ``sleep_until`` just moves simulated time forward.
    ``real_now`` and ``sleep`` can be replaced in tests.
    """

    def __init__(
        self,
        start: float,
        speed: float | str = 1.0,
        real_now: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if speed != "max" and (not isinstance(speed, int | float) or speed <= 0):
            raise ValueError(f"speed must be a positive number or 'max', got {speed!r}")
        self.start = float(start)
        self.speed = speed
        self._real_now = real_now
        self._sleep = sleep
        self._real_start = real_now()
        self._virtual = float(start)

    @property
    def is_max(self) -> bool:
        return self.speed == "max"

    def now(self) -> float:
        """Current simulated time in unix seconds."""
        if self.is_max:
            return self._virtual
        assert isinstance(self.speed, int | float)
        return self.start + (self._real_now() - self._real_start) * self.speed

    def sleep_until(self, t_sim: float) -> None:
        """Block until simulated time reaches ``t_sim`` (returns at once at ``max`` speed)."""
        if self.is_max:
            self._virtual = max(self._virtual, t_sim)
            return
        assert isinstance(self.speed, int | float)
        remaining = (t_sim - self.now()) / self.speed
        if remaining > 0:
            self._sleep(remaining)
