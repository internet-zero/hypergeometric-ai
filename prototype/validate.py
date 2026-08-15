#!/usr/bin/env python3
"""Milestone-0 prototype: ablation-grid migration check for one agent config.

Given a system prompt, a set of atomic rules cut from it, and two models
(incumbent A, candidate B), this script measures per-rule compliance with the
rule present vs. placebo-ablated, on both models, over generated probe
scenarios — then classifies every rule as DELETE / KEEP / REWRITE per model
and reports the A-vs-B diff with Wilson intervals and exact McNemar tests.

Scope (stated limitations of the prototype):
- Single-turn probes only; tool calls are captured but never executed.
- Mechanical checkers only — no LLM judges.
- Tier-2 realism is approximated with long synthetic contexts, not real traces.

Usage:
  python validate.py --selftest
  python validate.py --prompt example.prompt.txt --rules rules.example.yaml --dry-run
  python validate.py --prompt local/agent-insights.prompt.txt \
      --rules local/agent-insights.rules.yaml \
      --model-a gpt-5.6-luna --model-b gpt-5.6-sol --probes 30
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import json
import math
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

FILLER_SENTENCE = "This line is neutral placeholder text with no instruction content. "
DEFAULT_GENERATOR = "gpt-5.4-mini"
DEFAULT_THRESHOLD = 0.80
DEDUPE_SIMILARITY = 0.87
MAX_COMPLETION_TOKENS = 1600
CONCURRENCY = 8
RETRIES = 3

PLANTED_REDUNDANT = "Always respond in English."
PLANTED_LOAD_BEARING = (
    'Always include a top-level field "marker" with the exact value "HG-7" '
    "in your JSON response."
)


# --------------------------------------------------------------------------- data

@dataclass(frozen=True)
class Rule:
    id: str
    text: str
    checker: dict[str, Any]
    probe_hint: str = ""
    tools_enabled: bool = False
    planted: str | None = None  # None | "redundant" | "load_bearing"


@dataclass(frozen=True)
class RunResult:
    rule_id: str
    probe_idx: int
    arm: str          # "with" | "without"
    model: str
    complied: bool | None  # None = call failed after retries
    detail: str


@dataclass(frozen=True)
class ArmStats:
    passed: int
    total: int

    @property
    def rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


# --------------------------------------------------------------------------- checkers

def _strip_fences(text: str) -> str:
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    return m.group(1).strip() if m else text.strip()


def parse_json_loose(text: str) -> dict[str, Any] | None:
    candidate = _strip_fences(text)
    for attempt in (candidate, text.strip()):
        try:
            obj = json.loads(attempt)
            return obj if isinstance(obj, dict) else None
        except (json.JSONDecodeError, ValueError):
            pass
    start, end = candidate.find("{"), candidate.rfind("}")
    if 0 <= start < end:
        try:
            obj = json.loads(candidate[start:end + 1])
            return obj if isinstance(obj, dict) else None
        except (json.JSONDecodeError, ValueError):
            return None
    return None


def _get_field(obj: dict[str, Any], dotted: str) -> Any:
    current: Any = obj
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def check_json_object(text: str, _tc: list[dict], spec: dict) -> tuple[bool, str]:
    obj = parse_json_loose(text)
    if obj is None:
        return False, "output is not a JSON object"
    missing = [k for k in spec.get("required_keys", []) if k not in obj]
    if missing:
        return False, f"missing keys: {missing}"
    return True, "ok"


def check_field_required(text: str, _tc: list[dict], spec: dict) -> tuple[bool, str]:
    obj = parse_json_loose(text)
    if obj is None:
        return False, "output is not a JSON object"
    value = _get_field(obj, spec["field"])
    if value is None or (isinstance(value, (str, list, dict)) and not value):
        return False, f"field '{spec['field']}' absent or empty"
    return True, "ok"


def check_field_equals(text: str, _tc: list[dict], spec: dict) -> tuple[bool, str]:
    obj = parse_json_loose(text)
    if obj is None:
        return False, "output is not a JSON object"
    value = _get_field(obj, spec["field"])
    if value != spec["value"]:
        return False, f"field '{spec['field']}' != {spec['value']!r} (got {value!r})"
    return True, "ok"


def check_regex_must_not(text: str, _tc: list[dict], spec: dict) -> tuple[bool, str]:
    target = text
    if "json_field" in spec:
        obj = parse_json_loose(text)
        if obj is None:
            return False, "output is not a JSON object"
        value = _get_field(obj, spec["json_field"])
        target = value if isinstance(value, str) else json.dumps(value or "")
    m = re.search(spec["pattern"], target)
    if m:
        return False, f"forbidden pattern matched: {m.group(0)!r}"
    return True, "ok"


def check_regex_must(text: str, _tc: list[dict], spec: dict) -> tuple[bool, str]:
    target = text
    if "json_field" in spec:
        obj = parse_json_loose(text)
        if obj is None:
            return False, "output is not a JSON object"
        value = _get_field(obj, spec["json_field"])
        target = value if isinstance(value, str) else json.dumps(value or "")
    if re.search(spec["pattern"], target):
        return True, "ok"
    return False, f"required pattern not found: {spec['pattern']}"


def check_list_item_regex(text: str, _tc: list[dict], spec: dict) -> tuple[bool, str]:
    obj = parse_json_loose(text)
    if obj is None:
        return False, "output is not a JSON object"
    value = _get_field(obj, spec["field"])
    if not isinstance(value, list) or not value:
        return False, f"field '{spec['field']}' is not a non-empty list"
    pattern = spec["pattern"]
    for item in value:
        blob = json.dumps(item) if not isinstance(item, str) else item
        if re.search(pattern, blob):
            return True, "ok"
    return False, f"no item in '{spec['field']}' matches {pattern}"


def check_ascii_english(text: str, _tc: list[dict], _spec: dict) -> tuple[bool, str]:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False, "no letters in output"
    ratio = sum(1 for c in letters if c.isascii()) / len(letters)
    if ratio >= 0.9:
        return True, "ok"
    return False, f"non-ASCII letter ratio too high ({1 - ratio:.0%})"


def check_word_limit(text: str, _tc: list[dict], spec: dict) -> tuple[bool, str]:
    target = text
    if "json_field" in spec:
        obj = parse_json_loose(text)
        if obj is None:
            return False, "output is not a JSON object"
        value = _get_field(obj, spec["json_field"])
        target = value if isinstance(value, str) else json.dumps(value or "")
    count = len(target.split())
    if count <= spec["max_words"]:
        return True, "ok"
    return False, f"{count} words exceeds limit of {spec['max_words']}"


def check_first_tool_not_in(_text: str, tc: list[dict], spec: dict) -> tuple[bool, str]:
    if not tc:
        return True, "no tool call made (vacuously compliant)"
    first = tc[0]["name"]
    if first in spec["names"]:
        return False, f"first tool call was forbidden '{first}'"
    return True, f"first tool call '{first}' ok"


CHECKERS = {
    "json_object": check_json_object,
    "field_required": check_field_required,
    "field_equals": check_field_equals,
    "regex_must": check_regex_must,
    "regex_must_not": check_regex_must_not,
    "list_item_regex": check_list_item_regex,
    "ascii_english": check_ascii_english,
    "word_limit": check_word_limit,
    "first_tool_not_in": check_first_tool_not_in,
}


def run_checker(rule: Rule, text: str, tool_calls: list[dict]) -> tuple[bool, str]:
    spec = rule.checker
    return CHECKERS[spec["kind"]](text, tool_calls, spec)


# --------------------------------------------------------------------------- self-test

SELFTEST_CASES: list[tuple[dict, str, str]] = [
    ({"kind": "json_object", "required_keys": ["response"]},
     '{"response": "hi"}', "plain text answer"),
    ({"kind": "field_required", "field": "analysisExplanation"},
     '{"analysisExplanation": "queried saasSoftware"}', '{"analysisExplanation": ""}'),
    ({"kind": "field_equals", "field": "marker", "value": "HG-7"},
     '{"marker": "HG-7"}', '{"marker": "done"}'),
    ({"kind": "regex_must_not", "pattern": r"\$(match|group|sort)", "json_field": "response"},
     '{"response": "Total spend is $1.2M"}',
     '{"response": "pipeline: [{\\"$match\\": {}}]"}'),
    ({"kind": "list_item_regex", "field": "citations", "pattern": r'"ref":\s*"datasets\.'},
     '{"citations": [{"displayName": "SaaS", "ref": "datasets.saasSoftware"}]}',
     '{"citations": []}'),
    ({"kind": "ascii_english"}, "The total is 42 devices.", "Ответ полностью на русском языке."),
    ({"kind": "word_limit", "max_words": 5, "json_field": "answer"},
     '{"answer": "only four words here"}',
     '{"answer": "this answer clearly has far too many words for the limit"}'),
    ({"kind": "first_tool_not_in", "names": ["query_mongodb"]}, "", ""),
]


def self_test() -> int:
    failures = 0
    for spec, good, bad in SELFTEST_CASES:
        checker = CHECKERS[spec["kind"]]
        if spec["kind"] == "first_tool_not_in":
            ok_good, _ = checker("", [{"name": "count_mongodb", "arguments": "{}"}], spec)
            ok_bad, _ = checker("", [{"name": "query_mongodb", "arguments": "{}"}], spec)
        else:
            ok_good, _ = checker(good, [], spec)
            ok_bad, _ = checker(bad, [], spec)
        status = "PASS" if (ok_good and not ok_bad) else "FAIL"
        if status == "FAIL":
            failures += 1
        print(f"  [{status}] {spec['kind']}")
    print(f"self-test: {len(SELFTEST_CASES) - failures}/{len(SELFTEST_CASES)} checkers ok")
    return 1 if failures else 0


# --------------------------------------------------------------------------- statistics

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
    tail = sum(math.comb(n, i) for i in range(k + 1)) * (0.5 ** n)
    return min(1.0, 2 * tail)


def classify(with_stats: ArmStats, without_stats: ArmStats,
             threshold: float) -> tuple[str, bool]:
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


# --------------------------------------------------------------------------- config loading

def load_rules(path: Path) -> tuple[list[Rule], list[dict]]:
    doc = yaml.safe_load(path.read_text())
    rules = [
        Rule(
            id=r["id"],
            text=r["text"].rstrip("\n"),
            checker=r["checker"],
            probe_hint=r.get("probe_hint", ""),
            tools_enabled=bool(r.get("tools_enabled", False)),
            planted=r.get("planted"),
        )
        for r in doc["rules"]
    ]
    return rules, doc.get("tools", [])


def build_planted_rules() -> list[Rule]:
    return [
        Rule(
            id="planted-redundant",
            text=PLANTED_REDUNDANT,
            checker={"kind": "ascii_english"},
            probe_hint="any ordinary data question",
            planted="redundant",
        ),
        Rule(
            id="planted-load-bearing",
            text=PLANTED_LOAD_BEARING,
            checker={"kind": "field_equals", "field": "marker", "value": "HG-7"},
            probe_hint="any ordinary data question",
            planted="load_bearing",
        ),
    ]


def assemble_prompt(base_prompt: str, planted: list[Rule]) -> str:
    lines = "\n".join(f"- {r.text}" for r in planted)
    return f"{base_prompt}\n\n## Additional requirements\n\n{lines}\n"


def placebo_ablate(prompt: str, rule_text: str) -> str:
    if rule_text not in prompt:
        raise ValueError(f"rule text not found verbatim in prompt: {rule_text[:80]!r}")
    filler = (FILLER_SENTENCE * (len(rule_text) // len(FILLER_SENTENCE) + 1))[: len(rule_text)]
    return prompt.replace(rule_text, filler, 1)


# --------------------------------------------------------------------------- probe generation

GENERATION_INSTRUCTIONS = """You write test scenarios for an AI agent's rule compliance.

The agent's job: {agent_summary}

The rule under test: "{rule_text}"
Scenario guidance: {hint}

Write {n} distinct user messages that would each give the agent a genuine
opportunity to violate this rule (a compliant agent and a violating agent
would produce visibly different outputs). Vary phrasing, mood, and topic.
Make roughly one third of them "hard mode": long messages with the trigger
buried inside distracting context, or with user pressure pushing against
the rule.

Return ONLY a JSON object: {{"probes": ["message 1", "message 2", ...]}}"""


def dedupe(probes: list[str]) -> list[str]:
    kept: list[str] = []
    for p in probes:
        text = p.strip()
        if not text:
            continue
        if any(difflib.SequenceMatcher(None, text.lower(), k.lower()).ratio()
               > DEDUPE_SIMILARITY for k in kept):
            continue
        kept.append(text)
    return kept


async def generate_probes(client: Any, model: str, rule: Rule, n: int,
                          agent_summary: str) -> list[str]:
    prompt = GENERATION_INSTRUCTIONS.format(
        agent_summary=agent_summary, rule_text=rule.text.replace('"', "'"),
        hint=rule.probe_hint or "ordinary requests within the agent's domain", n=n,
    )
    resp = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_completion_tokens=4000,
    )
    obj = parse_json_loose(resp.choices[0].message.content or "")
    probes = obj.get("probes", []) if obj else []
    return dedupe([p for p in probes if isinstance(p, str)])[:n]


# --------------------------------------------------------------------------- grid execution

def tools_payload(tools: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get(
                    "parameters",
                    {"type": "object", "properties": {}, "additionalProperties": True},
                ),
            },
        }
        for t in tools
    ]


async def run_cell(client: Any, semaphore: asyncio.Semaphore, model: str,
                   system_prompt: str, probe: str,
                   tools: list[dict]) -> tuple[str, list[dict]] | None:
    async with semaphore:
        for attempt in range(RETRIES):
            try:
                kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": probe},
                    ],
                    "max_completion_tokens": MAX_COMPLETION_TOKENS,
                }
                if tools:
                    kwargs["tools"] = tools_payload(tools)
                resp = await client.chat.completions.create(**kwargs)
                msg = resp.choices[0].message
                calls = [
                    {"name": c.function.name, "arguments": c.function.arguments}
                    for c in (msg.tool_calls or [])
                ]
                return msg.content or "", calls
            except Exception as exc:  # noqa: BLE001 — API/network errors all retryable here
                if attempt == RETRIES - 1:
                    print(f"    call failed ({model}): {exc}", file=sys.stderr)
                    return None
                await asyncio.sleep(2 ** attempt)
    return None


async def run_grid(client: Any, rules: list[Rule], probes: dict[str, list[str]],
                   full_prompt: str, tools: list[dict], model_a: str, model_b: str,
                   k: int) -> list[RunResult]:
    semaphore = asyncio.Semaphore(CONCURRENCY)
    jobs: list[tuple[Rule, int, str, str, asyncio.Task]] = []
    async with asyncio.TaskGroup() as group:
        for rule in rules:
            ablated = placebo_ablate(full_prompt, rule.text)
            rule_tools = tools if rule.tools_enabled else []
            for idx, probe in enumerate(probes[rule.id]):
                for arm, prompt in (("with", full_prompt), ("without", ablated)):
                    for model in (model_a, model_b):
                        for _ in range(k):
                            task = group.create_task(
                                run_cell(client, semaphore, model, prompt, probe, rule_tools)
                            )
                            jobs.append((rule, idx, arm, model, task))
    results: list[RunResult] = []
    for rule, idx, arm, model, task in jobs:
        outcome = task.result()
        if outcome is None:
            results.append(RunResult(rule.id, idx, arm, model, None, "call failed"))
            continue
        text, calls = outcome
        ok, detail = run_checker(rule, text, calls)
        results.append(RunResult(rule.id, idx, arm, model, ok, detail))
    return results


# --------------------------------------------------------------------------- reporting

def arm_stats(results: list[RunResult], rule_id: str, arm: str, model: str) -> ArmStats:
    rows = [r for r in results
            if r.rule_id == rule_id and r.arm == arm and r.model == model
            and r.complied is not None]
    return ArmStats(passed=sum(r.complied for r in rows), total=len(rows))


def paired_discordants(results: list[RunResult], rule_id: str,
                       model_a: str, model_b: str) -> tuple[int, int]:
    by_probe: dict[int, dict[str, bool]] = {}
    for r in results:
        if r.rule_id == rule_id and r.arm == "with" and r.complied is not None:
            by_probe.setdefault(r.probe_idx, {})[r.model] = r.complied
    b = sum(1 for v in by_probe.values()
            if v.get(model_a) is True and v.get(model_b) is False)
    c = sum(1 for v in by_probe.values()
            if v.get(model_a) is False and v.get(model_b) is True)
    return b, c


def fmt_arm(s: ArmStats) -> str:
    lo, hi = wilson_interval(s.passed, s.total)
    return f"{s.passed}/{s.total} ({s.rate:.0%}, CI {lo:.0%}–{hi:.0%})"


def write_report(out_dir: Path, rules: list[Rule], results: list[RunResult],
                 model_a: str, model_b: str, threshold: float) -> str:
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
        b, c = paired_discordants(results, rule.id, model_a, model_b)
        p = mcnemar_exact(b, c)
        flag = " ⚠ borderline" if borderline else ""
        lines.append(
            f"| {rule.id} | {fmt_arm(aw)} | {fmt_arm(awo)} | {fmt_arm(bw)} | "
            f"{fmt_arm(bwo)} | **{verdict}**{flag} | b={b}, c={c}, p={p:.3f} |"
        )
        if rule.planted == "redundant" and verdict != "DELETE":
            control_failures.append(
                f"planted-redundant landed in {verdict} (expected DELETE) — harness bug?")
        if rule.planted == "load_bearing" and verdict != "KEEP":
            control_failures.append(
                f"planted-load-bearing landed in {verdict} (expected KEEP) — harness bug?")
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
    with (out_dir / "raw.jsonl").open("a") as fh:
        for r in results:
            fh.write(json.dumps(r.__dict__) + "\n")
    return report


# --------------------------------------------------------------------------- main

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prompt", type=Path, help="file containing the system prompt")
    p.add_argument("--rules", type=Path, help="YAML rule inventory")
    p.add_argument("--model-a", default="gpt-5.6-luna", help="incumbent model")
    p.add_argument("--model-b", default="gpt-5.6-sol", help="candidate model")
    p.add_argument("--generator", default=DEFAULT_GENERATOR,
                   help="probe generator model (should differ from A and B)")
    p.add_argument("--probes", type=int, default=30, help="probes per rule")
    p.add_argument("--k", type=int, default=1, help="repeats per probe (k=1: prefer more probes)")
    p.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    p.add_argument("--out", type=Path, default=Path("results"))
    p.add_argument("--dry-run", action="store_true", help="print the plan, no API calls")
    p.add_argument("--selftest", action="store_true", help="verify checkers offline")
    return p


async def async_main(args: argparse.Namespace) -> int:
    base_prompt = args.prompt.read_text()
    rules, tools = load_rules(args.rules)
    rules = rules + build_planted_rules()
    full_prompt = assemble_prompt(base_prompt, build_planted_rules())

    for rule in rules:
        placebo_ablate(full_prompt, rule.text)  # fail fast if any rule text drifts

    calls = len(rules) * args.probes * 2 * 2 * args.k
    print(f"plan: {len(rules)} rules ({len(rules) - 2} real + 2 planted) × "
          f"{args.probes} probes × 2 arms × 2 models × k={args.k} ≈ {calls} calls "
          f"(+ {len(rules)} generation calls on {args.generator})")
    if args.generator in (args.model_a, args.model_b):
        print("warning: generator model equals a model under test — "
              "the student is writing its own exam", file=sys.stderr)
    if args.dry_run:
        return 0

    from openai import AsyncOpenAI  # deferred: not needed for selftest/dry-run
    if not os.environ.get("OPENAI_API_KEY"):
        print("error: OPENAI_API_KEY is not set", file=sys.stderr)
        return 1
    client = AsyncOpenAI()

    print("generating probes…")
    agent_summary = base_prompt.splitlines()[0][:300]
    probes: dict[str, list[str]] = {}
    for rule in rules:
        probes[rule.id] = await generate_probes(
            client, args.generator, rule, args.probes, agent_summary)
        print(f"  {rule.id}: {len(probes[rule.id])} distinct probes")

    print("running grid…")
    results = await run_grid(client, rules, probes, full_prompt, tools,
                             args.model_a, args.model_b, args.k)
    failed = sum(1 for r in results if r.complied is None)
    if failed:
        print(f"warning: {failed}/{len(results)} calls failed and are excluded from n")

    report = write_report(args.out, rules, results, args.model_a, args.model_b,
                          args.threshold)
    print()
    print(report)
    print(f"written: {args.out / 'grid.md'} and {args.out / 'raw.jsonl'}")
    return 0


def main() -> int:
    args = build_arg_parser().parse_args()
    if args.selftest:
        return self_test()
    if not args.prompt or not args.rules:
        print("error: --prompt and --rules are required (or use --selftest)",
              file=sys.stderr)
        return 2
    return asyncio.run(async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
