"""Hypergeometric — statistical certification of agent-config migrations.

Public API re-exported here so callers (and the test suite) can use
``import hypergeometric as hg`` without knowing the module layout.
"""

from hypergeometric.checkers import (
    CHECKERS,
    SELFTEST_CASES,
    check_ascii_english,
    check_field_equals,
    check_field_required,
    check_first_tool_not_in,
    check_json_object,
    check_list_item_regex,
    check_regex_must,
    check_regex_must_not,
    check_tool_args_regex,
    check_tool_pipeline_single_key,
    check_word_limit,
    parse_json_loose,
    run_checker,
    self_test,
)
from hypergeometric.config import (
    assemble_prompt,
    build_arms,
    build_planted_rules,
    load_rules,
    load_skills,
    placebo_ablate,
)
from hypergeometric.constants import (
    DEFAULT_GENERATOR,
    DEFAULT_THRESHOLD,
    FILLER_SENTENCE,
    PLANTED_LOAD_BEARING,
    PLANTED_REDUNDANT,
)
from hypergeometric.grid import run_cell, run_grid, tools_payload
from hypergeometric.probes import dedupe, generate_probes
from hypergeometric.report import arm_stats, fmt_arm, paired_discordants, write_report
from hypergeometric.schemas import Arms, ArmStats, Rule, RunResult
from hypergeometric.stats import classify, mcnemar_exact, wilson_interval

__version__ = "0.1.0"

__all__ = [
    "CHECKERS",
    "SELFTEST_CASES",
    "check_ascii_english",
    "check_field_equals",
    "check_field_required",
    "check_first_tool_not_in",
    "check_json_object",
    "check_list_item_regex",
    "check_regex_must",
    "check_regex_must_not",
    "check_tool_args_regex",
    "check_tool_pipeline_single_key",
    "check_word_limit",
    "parse_json_loose",
    "run_checker",
    "self_test",
    "assemble_prompt",
    "build_arms",
    "build_planted_rules",
    "load_rules",
    "load_skills",
    "placebo_ablate",
    "DEFAULT_GENERATOR",
    "DEFAULT_THRESHOLD",
    "FILLER_SENTENCE",
    "PLANTED_LOAD_BEARING",
    "PLANTED_REDUNDANT",
    "run_cell",
    "run_grid",
    "tools_payload",
    "dedupe",
    "generate_probes",
    "arm_stats",
    "fmt_arm",
    "paired_discordants",
    "write_report",
    "Arms",
    "ArmStats",
    "Rule",
    "RunResult",
    "classify",
    "mcnemar_exact",
    "wilson_interval",
]
