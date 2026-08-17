"""Aggregation and the migration-grid report."""

from __future__ import annotations

import json
from pathlib import Path

from hypergeometric.schemas import ArmStats, Rule, RunResult
from hypergeometric.stats import classify, mcnemar_exact, wilson_interval


def write_probes(path: Path, run_id: str, probes: dict[str, list[str]]) -> None:
    """Persist the exact exam used for a run — the frozen, reusable asset.

    Without this file a verdict can't be audited ("which question was probe
    #7?") nor re-run against the identical probe set later.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"run_id": run_id, "probes": probes}, indent=1))


def arm_stats(results: list[RunResult], rule_id: str, arm: str, model: str) -> ArmStats:
    rows = [
        r
        for r in results
        if r.rule_id == rule_id and r.arm == arm and r.model == model and r.complied is not None
    ]
    return ArmStats(passed=sum(bool(r.complied) for r in rows), total=len(rows))


def paired_discordants(
    results: list[RunResult], rule_id: str, model_a: str, model_b: str
) -> tuple[int, int]:
    # Pair on (probe_idx, trial) so k > 1 repeats stay distinct pairs instead
    # of overwriting each other.
    by_pair: dict[tuple[int, int], dict[str, bool]] = {}
    for r in results:
        if r.rule_id == rule_id and r.arm == "with" and r.complied is not None:
            by_pair.setdefault((r.probe_idx, r.trial), {})[r.model] = r.complied
    b = sum(1 for v in by_pair.values() if v.get(model_a) is True and v.get(model_b) is False)
    c = sum(1 for v in by_pair.values() if v.get(model_a) is False and v.get(model_b) is True)
    return b, c


def fmt_arm(s: ArmStats) -> str:
    lo, hi = wilson_interval(s.passed, s.total)
    return f"{s.passed}/{s.total} ({s.rate:.0%}, CI {lo:.0%}–{hi:.0%})"


def write_report(
    out_dir: Path,
    rules: list[Rule],
    results: list[RunResult],
    model_a: str,
    model_b: str,
    threshold: float,
    run_id: str | None = None,
) -> str:
    lines = [
        "# Migration grid — ablation results",
        "",
        f"Incumbent (A): `{model_a}` · Candidate (B): `{model_b}` · "
        f"compliance threshold {threshold:.0%} · placebo ablation, k-paired probes",
        "",
        "| Rule | A with | A without | B with | B without | Verdict on B | McNemar A→B |",
        "|---|---|---|---|---|---|---|",
    ]
    control_failures: list[str] = []
    for rule in rules:
        aw = arm_stats(results, rule.id, "with", model_a)
        awo = arm_stats(results, rule.id, "without", model_a)
        bw = arm_stats(results, rule.id, "with", model_b)
        bwo = arm_stats(results, rule.id, "without", model_b)
        verdict, borderline = classify(bw, bwo, threshold)
        verdict_a, _ = classify(aw, awo, threshold)
        b, c = paired_discordants(results, rule.id, model_a, model_b)
        p = mcnemar_exact(b, c)
        flag = " ⚠ borderline" if borderline else ""
        lines.append(
            f"| {rule.id} | {fmt_arm(aw)} | {fmt_arm(awo)} | {fmt_arm(bw)} | "
            f"{fmt_arm(bwo)} | **{verdict}**{flag} | b={b}, c={c}, p={p:.3f} |"
        )
        # DESIGN.md control gate: planted verdicts must hold on BOTH models.
        expected = {"redundant": "DELETE", "load_bearing": "KEEP"}.get(rule.planted or "")
        if expected:
            for label, model_verdict in (("A", verdict_a), ("B", verdict)):
                if model_verdict != expected:
                    control_failures.append(
                        f"{rule.id} landed in {model_verdict} on model {label} "
                        f"(expected {expected}) — harness bug?"
                    )
    lines.append("")
    lines.append("## Controls")
    if control_failures:
        lines.extend(f"- **FAIL**: {c}" for c in control_failures)
        lines.append("- Do not interpret the real-rule verdicts until controls pass.")
    else:
        lines.append("- Both planted controls classified as expected. Instrument sane.")
    report = "\n".join(lines) + "\n"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "grid.md").write_text(report)
    # raw.jsonl is append-only by design (the durable run archive); run_id
    # keeps rows from different invocations distinguishable.
    with (out_dir / "raw.jsonl").open("a") as fh:
        for r in results:
            row = {**r.__dict__, "run_id": run_id} if run_id else r.__dict__
            fh.write(json.dumps(row) + "\n")
    return report
