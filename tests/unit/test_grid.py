"""Unit tests for grid call construction."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import hypergeometric as v


class KwargsCapturingClient:
    def __init__(self) -> None:
        self.captured: list[dict] = []

        async def create(**kwargs):
            self.captured.append(kwargs)
            message = SimpleNamespace(content=json.dumps({"ok": True}), tool_calls=None)
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))


TOOLS = [{"name": "t1", "description": "d", "parameters": {"type": "object", "properties": {}}}]


def test_tool_cells_disable_reasoning() -> None:
    client = KwargsCapturingClient()
    sem = asyncio.Semaphore(1)
    asyncio.run(v.run_cell(client, sem, "m", "sys", "probe", TOOLS))
    asyncio.run(v.run_cell(client, sem, "m", "sys", "probe", []))
    with_tools, without_tools = client.captured
    assert with_tools.get("reasoning_effort") == "none", "tools require reasoning off on chat API"
    assert "reasoning_effort" not in without_tools, "plain cells keep default reasoning"
    assert "tools" not in without_tools
