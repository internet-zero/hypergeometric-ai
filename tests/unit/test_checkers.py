"""Unit tests for every mechanical checker (instrument self-validation)."""

from __future__ import annotations

import hypergeometric as v


def test_selftest_all_checkers_pass() -> None:
    assert v.self_test() == 0


def test_every_registered_checker_has_a_selftest_case() -> None:
    covered = {spec["kind"] for spec, *_ in v.SELFTEST_CASES}
    assert covered == set(v.CHECKERS), (
        "every checker must prove it catches its violation before it may "
        f"judge a model; missing: {set(v.CHECKERS) - covered}"
    )


def test_tool_args_regex_vacuous_pass_when_uncalled() -> None:
    spec = {
        "kind": "tool_args_regex",
        "tool": "query_mongodb",
        "pattern": r'"filename"',
        "must": True,
    }
    ok, detail = v.check_tool_args_regex("", [], spec)
    assert ok and "vacuous" in detail


def test_tool_pipeline_single_key_ignores_calls_without_pipeline() -> None:
    spec = {"kind": "tool_pipeline_single_key", "tool": "query_mongodb"}
    calls = [{"name": "query_mongodb", "arguments": '{"collection": "x", "download": true}'}]
    ok, _ = v.check_tool_pipeline_single_key("", calls, spec)
    assert ok
