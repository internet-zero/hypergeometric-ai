"""Shared test helpers: a scripted fake model client with known ground truth.

Mirrors asato-svc's tests/tools.py convention — reusable helpers, no tests.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import validate as v

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

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))
