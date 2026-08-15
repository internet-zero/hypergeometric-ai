"""Unit tests for JSON extraction, probe dedupe, and source-aware ablation."""

from __future__ import annotations

from pathlib import Path

import pytest

import validate as v


def test_parse_json_loose() -> None:
    assert v.parse_json_loose('{"a": 1}') == {"a": 1}
    assert v.parse_json_loose('```json\n{"a": 1}\n```') == {"a": 1}
    assert v.parse_json_loose('Sure! {"a": 1} hope that helps') == {"a": 1}
    assert v.parse_json_loose("no json here") is None
    assert v.parse_json_loose("[1, 2, 3]") is None


def test_dedupe_collapses_near_paraphrases() -> None:
    probes = [
        "How many apps do we have?",
        "How many apps do we have??",
        "List vendors by total spend",
    ]
    assert len(v.dedupe(probes)) == 2


def test_placebo_ablate_preserves_length() -> None:
    prompt = "Header\n- Rule one text.\nFooter"
    out = v.placebo_ablate(prompt, "- Rule one text.")
    assert len(out) == len(prompt)
    assert "- Rule one text." not in out


def test_placebo_ablate_rejects_missing_text() -> None:
    with pytest.raises(ValueError):
        v.placebo_ablate("some prompt", "text that is not there")


# ------------------------------------------------------------- build_arms

PROMPT = "You are an assistant.\n- Always answer in JSON.\nEnd."
RULE_LINE = "- Always answer in JSON."
TOOLS = [
    {"name": "export_csv",
     "description": "Exports rows to CSV. BEFORE CALLING, verify: id_filter is set.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "other_tool", "description": "Unrelated.",
     "parameters": {"type": "object", "properties": {}}},
]


def test_build_arms_prompt_source() -> None:
    rule = v.Rule(id="r", text=RULE_LINE, checker={"kind": "ascii_english"})
    arms = v.build_arms(rule, PROMPT, TOOLS, {})
    assert RULE_LINE in arms.prompt_with
    assert RULE_LINE not in arms.prompt_without
    assert len(arms.prompt_with) == len(arms.prompt_without)
    assert arms.tools_with == () == arms.tools_without, "tools off unless tools_enabled"


def test_build_arms_tool_source_ablates_only_that_description() -> None:
    rule = v.Rule(id="r", text="BEFORE CALLING, verify: id_filter is set.",
                  checker={"kind": "ascii_english"}, source="tool:export_csv")
    arms = v.build_arms(rule, PROMPT, TOOLS, {})
    assert arms.prompt_with == arms.prompt_without == PROMPT
    with_desc = next(t for t in arms.tools_with if t["name"] == "export_csv")["description"]
    without_desc = next(t for t in arms.tools_without if t["name"] == "export_csv")["description"]
    assert "BEFORE CALLING" in with_desc and "BEFORE CALLING" not in without_desc
    assert len(with_desc) == len(without_desc)
    other = next(t for t in arms.tools_without if t["name"] == "other_tool")
    assert other["description"] == "Unrelated.", "other tools untouched"


def test_build_arms_skill_source(fixtures_dir: Path) -> None:
    skills = v.load_skills(fixtures_dir / "skills")
    assert "mini-skill" in skills
    rule_text = "- Always name export files in snake_case based on the user's request."
    rule = v.Rule(id="r", text=rule_text, checker={"kind": "ascii_english"},
                  source="skill:mini-skill")
    arms = v.build_arms(rule, PROMPT, TOOLS, skills)
    assert "## Skill: mini-skill (loaded)" in arms.prompt_with
    assert rule_text in arms.prompt_with
    assert rule_text not in arms.prompt_without
    assert len(arms.prompt_with) == len(arms.prompt_without)
    assert "Never invent records" in arms.prompt_without, "rest of skill intact"


def test_build_arms_unknown_sources_raise() -> None:
    rule = v.Rule(id="r", text="x", checker={"kind": "ascii_english"}, source="skill:nope")
    with pytest.raises(ValueError):
        v.build_arms(rule, PROMPT, TOOLS, {})
    rule2 = v.Rule(id="r2", text="x", checker={"kind": "ascii_english"}, source="tool:nope")
    with pytest.raises(ValueError):
        v.build_arms(rule2, PROMPT, TOOLS, {})
