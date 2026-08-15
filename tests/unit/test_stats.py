"""Unit tests for the statistics: Wilson, exact McNemar, cell classification."""

from __future__ import annotations

import hypergeometric as v


def test_wilson_edge_cases() -> None:
    assert v.wilson_interval(0, 0) == (0.0, 1.0)
    lo, hi = v.wilson_interval(10, 10)
    assert hi == 1.0 and 0.70 < lo < 0.75
    lo, hi = v.wilson_interval(5, 10)
    assert lo < 0.5 < hi


def test_mcnemar_exact() -> None:
    assert v.mcnemar_exact(0, 0) == 1.0
    assert abs(v.mcnemar_exact(10, 1) - 2 * (12 / 2048)) < 1e-9
    assert v.mcnemar_exact(3, 3) == 1.0
    assert v.mcnemar_exact(1, 10) == v.mcnemar_exact(10, 1)


def test_classify_cells() -> None:
    s = v.ArmStats
    assert v.classify(s(95, 100), s(95, 100), 0.8)[0] == "DELETE"
    assert v.classify(s(95, 100), s(20, 100), 0.8)[0] == "KEEP"
    assert v.classify(s(30, 100), s(20, 100), 0.8)[0] == "REWRITE"
    assert v.classify(s(30, 100), s(90, 100), 0.8)[0] == "FIX-URGENT"


def test_classify_no_data() -> None:
    verdict, borderline = v.classify(v.ArmStats(0, 0), v.ArmStats(0, 0), 0.8)
    assert verdict == "NO-DATA" and borderline


def test_classify_borderline_flag() -> None:
    _, borderline = v.classify(v.ArmStats(25, 30), v.ArmStats(5, 30), 0.8)
    assert borderline, "25/30 has a CI spanning the 80% threshold"
