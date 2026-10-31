"""Named random streams derived from ``(seed, stream_name)``.

Each stream is independent of every other, so adding a crew member (a new stream name) does not
change the numbers another member's streams produce.
"""

from __future__ import annotations

import hashlib

import numpy as np


def stream(seed: int, name: str) -> np.random.Generator:
    """Return a generator that depends only on ``seed`` and ``name``."""
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    key = tuple(int.from_bytes(digest[i : i + 4], "little") for i in range(0, 16, 4))
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence(seed, spawn_key=key)))
