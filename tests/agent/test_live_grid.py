"""Live grid smoke test against real models — integration-style.

Requires OPENAI_API_KEY, access to the models under test, and the
gitignored local/ config bundle (full agent config: system prompt, MCP tool
descriptions, skills). Never runs in CI — pyproject addopts ignores
tests/agent/, matching asato-svc's convention for env-dependent tests.

Run manually:
    OPENAI_API_KEY=... pytest tests/agent/ -s
Optional env: MODEL_A (default gpt-5.6-luna), MODEL_B (default gpt-5.6-sol),
LIVE_PROBES (default 5).
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

import hypergeometric as v

LOCAL = Path(__file__).resolve().parents[2] / "local" / "agent-insights"

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY") or not LOCAL.is_dir(),
    reason="needs OPENAI_API_KEY and the local/agent-insights config bundle",
)


def test_live_small_grid(tmp_path: Path) -> None:
    from openai import AsyncOpenAI

    model_a = os.environ.get("MODEL_A", "gpt-5.6-luna")
    model_b = os.environ.get("MODEL_B", "gpt-5.6-sol")
    n_probes = int(os.environ.get("LIVE_PROBES", "5"))

    base_prompt = (LOCAL / "system.prompt.txt").read_text()
    rules, tools = v.load_rules(LOCAL / "rules.yaml")
    skills = v.load_skills(LOCAL / "skills")
    planted = v.build_planted_rules()
    # Smoke scope: one cheap prompt rule + the load-bearing control.
    subset = [next(r for r in rules if r.id == "R2-analysis-explanation-required"), planted[1]]
    full_prompt = v.assemble_prompt(base_prompt, planted)
    for rule in subset:
        v.build_arms(rule, full_prompt, tools, skills)

    client = AsyncOpenAI()

    async def go():
        probes = {
            r.id: await v.generate_probes(
                client, v.DEFAULT_GENERATOR, r, n_probes, base_prompt.splitlines()[0]
            )
            for r in subset
        }
        results = await v.run_grid(
            client, subset, probes, full_prompt, tools, skills, model_a, model_b, 1
        )
        return results

    results = asyncio.run(go())
    completed = [r for r in results if r.complied is not None]
    assert completed, "at least some live calls must succeed"
    report = v.write_report(tmp_path, subset, results, model_a, model_b, 0.8)
    # The load-bearing control is the live instrument check: with the rule
    # present, models should emit the marker far more often than without it.
    with_arm = v.arm_stats(results, "planted-load-bearing", "with", model_b)
    without_arm = v.arm_stats(results, "planted-load-bearing", "without", model_b)
    assert with_arm.rate > without_arm.rate, (
        f"marker rule shows no effect on {model_b}: "
        f"with={with_arm.rate:.0%} without={without_arm.rate:.0%}\n{report}"
    )
