"""Statistics: Wilson intervals, exact McNemar, and cell classification."""

from __future__ import annotations

import math

from hypergeometric.schemas import ArmStats


def wilson_interval(passed: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return 0.0, 1.0
    p = passed / total
    denom = 1 + z * z / total
    centre = p + z * z / (2 * total)
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    return max(0.0, (centre - margin) / denom), min(1.0, (centre + margin) / denom)


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value on discordant pair counts b, c."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) * (0.5**n)
    return min(1.0, 2 * tail)


def classify(with_stats: ArmStats, without_stats: ArmStats, threshold: float) -> tuple[str, bool]:
    """Return (verdict, borderline). Cells per DESIGN.md §2.7."""
    w_lo, w_hi = wilson_interval(with_stats.passed, with_stats.total)
    wo_lo, wo_hi = wilson_interval(without_stats.passed, without_stats.total)
    borderline = (w_lo < threshold < w_hi) or (wo_lo < threshold < wo_hi)
    complies_with = with_stats.rate >= threshold
    complies_without = without_stats.rate >= threshold
    if complies_with and complies_without:
        return "DELETE", borderline
    if complies_with:
        return "KEEP", borderline
    if complies_without:
        return "FIX-URGENT", borderline
    return "REWRITE", borderline
