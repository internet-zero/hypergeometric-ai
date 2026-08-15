"""Immutable data types for rules, experimental arms, and run records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Rule:
    id: str
    text: str
    checker: dict[str, Any]
    probe_hint: str = ""
    tools_enabled: bool = False
    planted: str | None = None  # None | "redundant" | "load_bearing"
    source: str = "prompt"  # "prompt" | "tool:<name>" | "skill:<name>"


@dataclass(frozen=True)
class Arms:
    """The two experimental arms for one rule: rule present vs. placebo-ablated.

    Ablation happens in whichever artifact the rule lives in — the system
    prompt, an MCP tool description, or a skill file — never anywhere else.
    """

    prompt_with: str
    prompt_without: str
    tools_with: tuple[dict, ...]
    tools_without: tuple[dict, ...]


@dataclass(frozen=True)
class RunResult:
    rule_id: str
    probe_idx: int
    arm: str  # "with" | "without"
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
