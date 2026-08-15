"""Config loading and source-aware placebo ablation.

A rule lives in one of three artifacts — the system prompt, an MCP tool
description, or a skill file — and its ablation happens only there.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from hypergeometric.constants import (
    FILLER_SENTENCE,
    PLANTED_LOAD_BEARING,
    PLANTED_REDUNDANT,
)
from hypergeometric.schemas import Arms, Rule


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
            source=r.get("source", "prompt"),
        )
        for r in doc["rules"]
    ]
    if "tools_file" in doc:
        tools_doc = yaml.safe_load((path.parent / doc["tools_file"]).read_text())
        return rules, tools_doc.get("tools", [])
    return rules, doc.get("tools", [])


def load_skills(skills_dir: Path | None) -> dict[str, str]:
    """Map skill name -> SKILL.md text for every <skills_dir>/<name>/SKILL.md."""
    if skills_dir is None:
        return {}
    return {
        child.name: (child / "SKILL.md").read_text()
        for child in sorted(skills_dir.iterdir())
        if (child / "SKILL.md").is_file()
    }


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


def build_arms(rule: Rule, full_prompt: str, tools: list[dict], skills: dict[str, str]) -> Arms:
    """Build the with/without arms, ablating in the rule's own source artifact."""
    base_tools = tuple(tools) if rule.tools_enabled else ()

    if rule.source == "prompt":
        return Arms(full_prompt, placebo_ablate(full_prompt, rule.text), base_tools, base_tools)

    if rule.source.startswith("skill:"):
        name = rule.source.split(":", 1)[1]
        if name not in skills:
            raise ValueError(f"rule {rule.id}: unknown skill '{name}' (--skills-dir?)")
        section = f"\n\n## Skill: {name} (loaded)\n\n"
        return Arms(
            full_prompt + section + skills[name],
            full_prompt + section + placebo_ablate(skills[name], rule.text),
            base_tools,
            base_tools,
        )

    if rule.source.startswith("tool:"):
        name = rule.source.split(":", 1)[1]
        if not any(t["name"] == name for t in tools):
            raise ValueError(f"rule {rule.id}: unknown tool '{name}' in rules yaml")
        ablated = tuple(
            (
                {**t, "description": placebo_ablate(t.get("description", ""), rule.text)}
                if t["name"] == name
                else t
            )
            for t in tools
        )
        return Arms(full_prompt, full_prompt, tuple(tools), ablated)

    raise ValueError(f"rule {rule.id}: unknown source '{rule.source}'")
