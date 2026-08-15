#!/usr/bin/env python3
"""Offline tests for validate.py — no API key, no network.

Run: python test_validate.py    (also collectable by pytest)

Covers: every mechanical checker, the statistics (Wilson, exact McNemar,
cell classification), placebo ablation, JSON extraction, probe dedupe, and
an end-to-end grid run against a scripted fake model client with known
ground-truth verdicts (including both planted controls).
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import validate as v

HERE = Path(__file__).parent


# --------------------------------------------------------------------------- units

def test_selftest_checkers() -> None:
    assert v.self_test() == 0


def test_wilson() -> None:
    assert v.wilson_interval(0, 0) == (0.0, 1.0)
    lo, hi = v.wilson_interval(10, 10)
    assert hi == 1.0 and 0.70 < lo < 0.75
    lo, hi = v.wilson_interval(5, 10)
    assert lo < 0.5 < hi


def test_mcnemar() -> None:
    assert v.mcnemar_exact(0, 0) == 1.0
    assert abs(v.mcnemar_exact(10, 1) - 2 * (12 / 2048)) < 1e-9
    assert v.mcnemar_exact(3, 3) == 1.0
    assert v.mcnemar_exact(1, 10) == v.mcnemar_exact(10, 1)


def test_classify() -> None:
    s = v.ArmStats
    assert v.classify(s(95, 100), s(95, 100), 0.8)[0] == "DELETE"
    assert v.classify(s(95, 100), s(20, 100), 0.8)[0] == "KEEP"
    assert v.classify(s(30, 100), s(20, 100), 0.8)[0] == "REWRITE"
    assert v.classify(s(30, 100), s(90, 100), 0.8)[0] == "FIX-URGENT"
    _, borderline = v.classify(s(25, 30), s(5, 30), 0.8)
    assert borderline, "25/30 has a CI spanning the 80% threshold"


def test_placebo_ablate() -> None:
    prompt = "Header\n- Rule one text.\nFooter"
    out = v.placebo_ablate(prompt, "- Rule one text.")
    assert len(out) == len(prompt)
    assert "- Rule one text." not in out
    try:
        v.placebo_ablate(prompt, "not in prompt")
        raise AssertionError("expected ValueError for missing rule text")
    except ValueError:
        pass


def test_parse_json_loose() -> None:
    assert v.parse_json_loose('{"a": 1}') == {"a": 1}
    assert v.parse_json_loose('```json\n{"a": 1}\n```') == {"a": 1}
    assert v.parse_json_loose('Sure! {"a": 1} hope that helps') == {"a": 1}
    assert v.parse_json_loose("no json here") is None
    assert v.parse_json_loose("[1, 2, 3]") is None


def test_dedupe() -> None:
    probes = [
        "How many apps do we have?",
        "How many apps do we have??",
        "List vendors by total spend",
    ]
    assert len(v.dedupe(probes)) == 2


# --------------------------------------------------------------------------- fake client

GEN_MODEL = "fake-generator"
LONG_ANSWER = " ".join(["word"] * 220)
DISTINCT_PROBES = [
    "What is the total cost of our software portfolio this quarter?",
    "Which applications have zero active users right now?",
    "Give me a breakdown of devices by operating system.",
    "Who are our five most expensive vendors?",
    "List entitlements expiring within thirty days.",
    "How many laptops were added to inventory last month?",
    "Show shadow IT applications discovered this year.",
    "Compare license utilization between engineering and sales.",
]


def _response(content: str):
    message = SimpleNamespace(content=content, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def make_behavior(rule_text: dict[str, str]):
    """Scripted model behavior with known ground truth.

    model-a: every real rule is load-bearing (complies iff rule present).
    model-b: R1 native (DELETE), R2 broken even with the rule (REWRITE),
             R3 load-bearing (KEEP). Both models honor the planted marker
             only when its rule is present, and always answer in English.
    """

    def behavior(**kwargs):
        model = kwargs["model"]
        if model == GEN_MODEL:
            return _response(json.dumps({"probes": DISTINCT_PROBES}))
        system = kwargs["messages"][0]["content"]
        has = {rid: text in system for rid, text in rule_text.items()}
        marker_present = v.PLANTED_LOAD_BEARING in system

        if model == "model-a":
            if not has["R1"]:
                return _response("the answer is 42, plain and simple")
            if not has["R3"]:
                answer = LONG_ANSWER
            elif not has["R2"]:
                answer = 'computed with a {"$match": {...}} stage on db.software'
            else:
                answer = "Total spend is 1.2M across 240 applications."
        else:  # model-b
            if not has["R3"]:
                answer = LONG_ANSWER
            else:
                answer = 'derived via {"$match": {}} then {"$group": {}}'
        obj: dict[str, object] = {"answer": answer, "sources": ["inventory-db"]}
        if marker_present:
            obj["marker"] = "HG-7"
        return _response(json.dumps(obj))

    return behavior


class FakeClient:
    def __init__(self, behavior) -> None:
        async def create(**kwargs):
            return behavior(**kwargs)

        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=create))


# --------------------------------------------------------------------------- end-to-end

def test_end_to_end_grid() -> None:
    rules, tools = v.load_rules(HERE / "rules.example.yaml")
    base_prompt = (HERE / "example.prompt.txt").read_text()
    planted = v.build_planted_rules()
    all_rules = rules + planted
    full_prompt = v.assemble_prompt(base_prompt, planted)

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
        results = await v.run_grid(client, all_rules, probes, full_prompt, tools,
                                   "model-a", "model-b", 1)
        return probes, results

    probes, results = asyncio.run(go())
    assert all(len(p) == 8 for p in probes.values()), "8 distinct probes per rule"
    assert all(r.complied is not None for r in results), "no failed calls offline"

    out_dir = Path(tempfile.mkdtemp())
    report = v.write_report(out_dir, all_rules, results, "model-a", "model-b", 0.8)

    def row(rule_id: str) -> str:
        return next(l for l in report.splitlines() if l.startswith(f"| {rule_id} "))

    assert "**DELETE**" in row("R1-json-contract"), "B does JSON natively"
    assert "**REWRITE**" in row("R2-no-query-syntax"), "B leaks pipelines even with rule"
    assert "**KEEP**" in row("R3-word-limit"), "B needs the word limit"
    assert "**DELETE**" in row("planted-redundant")
    assert "**KEEP**" in row("planted-load-bearing")
    assert "Instrument sane" in report, "both controls must classify correctly"

    a_with = v.arm_stats(results, "R2-no-query-syntax", "with", "model-a")
    a_without = v.arm_stats(results, "R2-no-query-syntax", "without", "model-a")
    assert a_with.rate == 1.0 and a_without.rate == 0.0, "A: R2 load-bearing"

    b, c = v.paired_discordants(results, "R2-no-query-syntax", "model-a", "model-b")
    assert b == 8 and c == 0, "all discordant pairs are A-pass/B-fail"
    assert v.mcnemar_exact(b, c) < 0.01, "regression is significant at n=8"

    assert (out_dir / "grid.md").exists() and (out_dir / "raw.jsonl").exists()


# --------------------------------------------------------------------------- runner

def main() -> int:
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    failures = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  [PASS] {name}")
        except AssertionError as exc:
            failures += 1
            print(f"  [FAIL] {name}: {exc}")
    print(f"{len(tests) - failures}/{len(tests)} tests passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
