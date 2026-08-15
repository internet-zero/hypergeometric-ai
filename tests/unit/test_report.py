"""Unit tests for aggregation and report writing."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import hypergeometric as v


def _rr(model: str, complied: bool, probe_idx: int = 0, trial: int = 0) -> v.RunResult:
    return v.RunResult("R", probe_idx, "with", model, complied, "x", trial)


def test_paired_discordants_keeps_repeats_distinct() -> None:
    # k=2: trial 0 is discordant (A pass / B fail), trial 1 is concordant.
    results = [
        _rr("model-a", True, trial=0),
        _rr("model-b", False, trial=0),
        _rr("model-a", False, trial=1),
        _rr("model-b", False, trial=1),
    ]
    b, c = v.paired_discordants(results, "R", "model-a", "model-b")
    assert (b, c) == (1, 0), "each (probe, trial) repeat must count as its own pair"


def test_write_report_stamps_run_id() -> None:
    rule = v.Rule(id="R", text="- Rule.", checker={"kind": "ascii_english"})
    results = [
        v.RunResult("R", 0, arm, model, True, "ok")
        for arm in ("with", "without")
        for model in ("model-a", "model-b")
    ]
    out = Path(tempfile.mkdtemp())
    v.write_report(out, [rule], results, "model-a", "model-b", 0.8, run_id="test-run")
    rows = [json.loads(line) for line in (out / "raw.jsonl").read_text().splitlines()]
    assert rows and all(r["run_id"] == "test-run" for r in rows)
