"""Shared loading of ``sim/params/*.yaml``: every parameter is ``{value, source, ...}``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

PARAMS_DIR = Path(__file__).resolve().parents[2] / "params"


class ParamsError(ValueError):
    """Raised when a parameter file is malformed or a parameter has no source."""


def flatten(block: dict[str, Any], where: str) -> dict[str, float]:
    """Turn ``{name: {value, source}}`` into ``{name: value}``, requiring a source on each."""
    out: dict[str, float] = {}
    for name, leaf in block.items():
        if not isinstance(leaf, dict) or "value" not in leaf or not leaf.get("source"):
            raise ParamsError(f"{where}.{name} needs a value and a source")
        out[name] = float(leaf["value"])
    return out


def load_block(path: Path, key: str = "defaults") -> dict[str, float]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return flatten(raw[key], key)
