"""Command-line entry point: plan, self-test, or run the ablation grid.

Usage:
  hypergeometric --selftest
  hypergeometric --prompt examples/example.prompt.txt \\
      --rules examples/rules.example.yaml --dry-run
  hypergeometric --prompt local/agent-insights/system.prompt.txt \\
      --rules local/agent-insights/rules.yaml \\
      --skills-dir local/agent-insights/skills \\
      --model-a gpt-5.6-luna --model-b gpt-5.6-sol --probes 30
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from hypergeometric.checkers import self_test
from hypergeometric.config import (
    assemble_prompt,
    build_arms,
    build_planted_rules,
    load_rules,
    load_skills,
)
from hypergeometric.constants import DEFAULT_GENERATOR, DEFAULT_THRESHOLD
from hypergeometric.grid import run_grid
from hypergeometric.probes import generate_probes
from hypergeometric.report import write_report


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prompt", type=Path, help="file containing the system prompt")
    p.add_argument("--rules", type=Path, help="YAML rule inventory")
    p.add_argument(
        "--skills-dir",
        type=Path,
        default=None,
        help="directory of <skill>/SKILL.md files (for skill-source rules)",
    )
    p.add_argument("--model-a", default="gpt-5.6-luna", help="incumbent model")
    p.add_argument("--model-b", default="gpt-5.6-sol", help="candidate model")
    p.add_argument(
        "--generator",
        default=DEFAULT_GENERATOR,
        help="probe generator model (should differ from A and B)",
    )
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
    skills = load_skills(args.skills_dir)
    rules = rules + build_planted_rules()
    full_prompt = assemble_prompt(base_prompt, build_planted_rules())

    for rule in rules:
        build_arms(rule, full_prompt, tools, skills)  # fail fast if any rule text drifts

    calls = len(rules) * args.probes * 2 * 2 * args.k
    print(
        f"plan: {len(rules)} rules ({len(rules) - 2} real + 2 planted) × "
        f"{args.probes} probes × 2 arms × 2 models × k={args.k} ≈ {calls} calls "
        f"(+ {len(rules)} generation calls on {args.generator})"
    )
    if args.generator in (args.model_a, args.model_b):
        print(
            "warning: generator model equals a model under test — "
            "the student is writing its own exam",
            file=sys.stderr,
        )
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
            client, args.generator, rule, args.probes, agent_summary
        )
        print(f"  {rule.id}: {len(probes[rule.id])} distinct probes")

    print("running grid…")
    results = await run_grid(
        client, rules, probes, full_prompt, tools, skills, args.model_a, args.model_b, args.k
    )
    failed = sum(1 for r in results if r.complied is None)
    if failed:
        print(f"warning: {failed}/{len(results)} calls failed and are excluded from n")

    run_id = f"{args.model_a}->{args.model_b}@{datetime.now(UTC).isoformat(timespec='seconds')}"
    report = write_report(
        args.out, rules, results, args.model_a, args.model_b, args.threshold, run_id=run_id
    )
    print()
    print(report)
    print(f"written: {args.out / 'grid.md'} and {args.out / 'raw.jsonl'}")
    return 0


def main() -> int:
    args = build_arg_parser().parse_args()
    if args.selftest:
        return self_test()
    if not args.prompt or not args.rules:
        print("error: --prompt and --rules are required (or use --selftest)", file=sys.stderr)
        return 2
    return asyncio.run(async_main(args))
