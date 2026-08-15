"""End-to-end offline grid run against the scripted fake client.

Ground truth is built into the fake behavior (tests/tools.py): model-b does
JSON natively (DELETE), leaks pipelines even with the rule (REWRITE), and
needs the word limit (KEEP). Both planted controls must classify correctly.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import hypergeometric as v
from tests.tools import DISTINCT_PROBES, GEN_MODEL, FakeClient, make_behavior


def _run(example_rules, example_prompt):
    rules, tools = example_rules
    planted = v.build_planted_rules()
    all_rules = rules + planted
    full_prompt = v.assemble_prompt(example_prompt, planted)
    rule_text = {
        "R1": next(r.text for r in rules if r.id == "R1-json-contract"),
        "R2": next(r.text for r in rules if r.id == "R2-no-query-syntax"),
        "R3": next(r.text for r in rules if r.id == "R3-word-limit"),
    }
    client = FakeClient(make_behavior(rule_text))

    async def go():
        probes = {
            r.id: await v.generate_probes(client, GEN_MODEL, r, 8, "inventory agent")
            for r in all_rules
        }
        results = await v.run_grid(
            client, all_rules, probes, full_prompt, tools, {}, "model-a", "model-b", 1
        )
        return probes, results

    probes, results = asyncio.run(go())
    return all_rules, probes, results


def test_end_to_end_grid(example_rules, example_prompt) -> None:
    all_rules, probes, results = _run(example_rules, example_prompt)
    assert all(len(p) == len(DISTINCT_PROBES) for p in probes.values())
    assert all(r.complied is not None for r in results), "no failed calls offline"
    assert all(r.output for r in results), "every result must carry the model's actual output"

    out_dir = Path(tempfile.mkdtemp())
    report = v.write_report(out_dir, all_rules, results, "model-a", "model-b", 0.8)

    def row(rule_id: str) -> str:
        return next(line for line in report.splitlines() if line.startswith(f"| {rule_id} "))

    assert "**DELETE**" in row("R1-json-contract"), "B does JSON natively"
    assert "**REWRITE**" in row("R2-no-query-syntax"), "B leaks pipelines even with rule"
    assert "**KEEP**" in row("R3-word-limit"), "B needs the word limit"
    assert "**DELETE**" in row("planted-redundant")
    assert "**KEEP**" in row("planted-load-bearing")
    assert "Instrument sane" in report, "both controls must classify correctly"
    assert (out_dir / "grid.md").exists() and (out_dir / "raw.jsonl").exists()


def test_regression_is_statistically_visible(example_rules, example_prompt) -> None:
    _, _, results = _run(example_rules, example_prompt)
    a_with = v.arm_stats(results, "R2-no-query-syntax", "with", "model-a")
    a_without = v.arm_stats(results, "R2-no-query-syntax", "without", "model-a")
    assert a_with.rate == 1.0 and a_without.rate == 0.0, "A: R2 load-bearing"
    b, c = v.paired_discordants(results, "R2-no-query-syntax", "model-a", "model-b")
    assert b == 8 and c == 0, "all discordant pairs are A-pass/B-fail"
    assert v.mcnemar_exact(b, c) < 0.01, "regression significant even at n=8"
