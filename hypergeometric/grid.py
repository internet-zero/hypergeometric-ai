"""The ablation grid: run every probe through both arms on both models."""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from hypergeometric.checkers import run_checker
from hypergeometric.config import build_arms
from hypergeometric.constants import CONCURRENCY, MAX_COMPLETION_TOKENS, RETRIES
from hypergeometric.schemas import Rule, RunResult


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


async def run_cell(
    client: Any,
    semaphore: asyncio.Semaphore,
    model: str,
    system_prompt: str,
    probe: str,
    tools: list[dict],
) -> tuple[str, list[dict]] | None:
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
                await asyncio.sleep(2**attempt)
    return None


async def run_grid(
    client: Any,
    rules: list[Rule],
    probes: dict[str, list[str]],
    full_prompt: str,
    tools: list[dict],
    skills: dict[str, str],
    model_a: str,
    model_b: str,
    k: int,
) -> list[RunResult]:
    semaphore = asyncio.Semaphore(CONCURRENCY)
    jobs: list[tuple[Rule, int, str, str, asyncio.Task]] = []
    async with asyncio.TaskGroup() as group:
        for rule in rules:
            arms = build_arms(rule, full_prompt, tools, skills)
            arm_setup = (
                ("with", arms.prompt_with, list(arms.tools_with)),
                ("without", arms.prompt_without, list(arms.tools_without)),
            )
            for idx, probe in enumerate(probes[rule.id]):
                for arm, prompt, arm_tools in arm_setup:
                    for model in (model_a, model_b):
                        for _ in range(k):
                            task = group.create_task(
                                run_cell(client, semaphore, model, prompt, probe, arm_tools)
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
