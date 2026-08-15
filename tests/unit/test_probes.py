"""Unit tests for probe generation robustness."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import hypergeometric as v


class FlakyClient:
    """Fails the first call with a transient error, then succeeds."""

    def __init__(self) -> None:
        self.calls = 0

        async def create(**_kwargs):
            self.calls += 1
            if self.calls == 1:
                raise ConnectionError("transient")
            content = json.dumps({"probes": ["What is our total software spend?"]})
            message = SimpleNamespace(content=content, tool_calls=None)
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))


def test_generate_probes_retries_transient_errors() -> None:
    client = FlakyClient()
    rule = v.Rule(id="R", text="- Rule.", checker={"kind": "ascii_english"})
    probes = asyncio.run(v.generate_probes(client, "gen", rule, 5, "agent"))
    assert client.calls == 2, "first failure must be retried, not fatal"
    assert probes == ["What is our total software spend?"]
