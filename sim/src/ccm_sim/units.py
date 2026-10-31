"""CO2 unit conversion (D4): partial pressure in mmHg from a ppm mixing ratio."""

from __future__ import annotations

DEFAULT_CABIN_PRESSURE_MMHG = 760.0


def ppm_to_mmhg(ppm: float, pressure_mmhg: float = DEFAULT_CABIN_PRESSURE_MMHG) -> float:
    """Return CO2 partial pressure in mmHg: ppm x 1e-6 x cabin pressure."""
    return ppm * 1e-6 * pressure_mmhg


def mmhg_to_ppm(mmhg: float, pressure_mmhg: float = DEFAULT_CABIN_PRESSURE_MMHG) -> float:
    """Inverse of :func:`ppm_to_mmhg`."""
    return mmhg / (1e-6 * pressure_mmhg)
