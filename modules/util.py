"""Small shared utilities."""
from __future__ import annotations

import hashlib
import random


def seeded_rng(*parts: str) -> random.Random:
    """Return a ``random.Random`` seeded deterministically from ``parts``.

    Used by the data-fetch modules to produce stable mock figures for a given
    category until real data sources (Amazon, Google Trends, ...) are wired in.
    """
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))
