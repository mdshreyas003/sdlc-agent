"""Bootstrap statistics for the scoreboard.

Ported from the legacy scorer (reference only): a 95% percentile bootstrap that resamples
questions, and a paired difference over the questions two systems both answered. Every call
reseeds, so the same inputs always print the same table.
"""

from __future__ import annotations

import math
import random
import statistics
from collections.abc import Mapping, Sequence
from typing import Literal

Interval = tuple[float, float, float]
N_BOOT = 1000
SEED = 0


def boot(values: Sequence[float], n: int = N_BOOT, seed: int = SEED) -> Interval:
    """Mean of `values` and its 95% bootstrap interval (resampling questions)."""
    if not values:
        return math.nan, math.nan, math.nan
    values = list(values)
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choices(values, k=len(values))) for _ in range(n))
    return statistics.fmean(values), means[int(0.025 * n)], means[int(0.975 * n) - 1]


def boot_diff(a: Mapping[str, float], b: Mapping[str, float], n: int = N_BOOT, seed: int = SEED) -> Interval:
    """Paired difference a - b over the question ids both systems answered."""
    shared = sorted(a.keys() & b.keys())
    return boot([a[k] - b[k] for k in shared], n, seed)


def fmt(interval: Interval, kind: Literal["pct", "diff", "num", "usd"] = "pct") -> str:
    """`pct` for rates, `diff` for a paired difference of rates (percentage points), `num`, `usd`."""
    mean, lo, hi = interval
    if math.isnan(mean):
        return "-"
    if kind == "diff":
        return f"{mean * 100:+.0f} pts [{lo * 100:+.0f}, {hi * 100:+.0f}]"
    if kind == "pct":
        return f"{mean * 100:.0f}% [{lo * 100:.0f}-{hi * 100:.0f}]"
    if kind == "usd":
        return f"${mean:.4f} [{lo:.4f}-{hi:.4f}]"
    return f"{mean:.2f} [{lo:.2f}-{hi:.2f}]"
