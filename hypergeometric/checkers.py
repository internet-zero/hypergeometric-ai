"""Mechanical compliance checkers and their self-test cases.

Every checker registered in CHECKERS must have a SELFTEST_CASES entry proving
it catches its violation and passes compliance — enforced by the test suite.
No LLM judges anywhere in this module by design.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from hypergeometric.schemas import Rule

CheckerFn = Callable[[str, list[dict], dict], tuple[bool, str]]


def _strip_fences(text: str) -> str:
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    return m.group(1).strip() if m else text.strip()


def parse_json_loose(text: str) -> dict[str, Any] | None:
    candidate = _strip_fences(text)
    for attempt in (candidate, text.strip()):
        try:
            obj = json.loads(attempt)
            return obj if isinstance(obj, dict) else None
        except (json.JSONDecodeError, ValueError):
            pass
    start, end = candidate.find("{"), candidate.rfind("}")
    if 0 <= start < end:
        try:
            obj = json.loads(candidate[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except (json.JSONDecodeError, ValueError):
            return None
    return None


def _get_field(obj: dict[str, Any], dotted: str) -> Any:
    current: Any = obj
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def check_json_object(text: str, _tc: list[dict], spec: dict) -> tuple[bool, str]:
    obj = parse_json_loose(text)
    if obj is None:
        return False, "output is not a JSON object"
    missing = [k for k in spec.get("required_keys", []) if k not in obj]
    if missing:
        return False, f"missing keys: {missing}"
    return True, "ok"


def check_field_required(text: str, _tc: list[dict], spec: dict) -> tuple[bool, str]:
    obj = parse_json_loose(text)
    if obj is None:
        return False, "output is not a JSON object"
    value = _get_field(obj, spec["field"])
    if value is None or (isinstance(value, (str, list, dict)) and not value):
        return False, f"field '{spec['field']}' absent or empty"
    return True, "ok"


def check_field_equals(text: str, _tc: list[dict], spec: dict) -> tuple[bool, str]:
    obj = parse_json_loose(text)
    if obj is None:
        return False, "output is not a JSON object"
    value = _get_field(obj, spec["field"])
    if value != spec["value"]:
        return False, f"field '{spec['field']}' != {spec['value']!r} (got {value!r})"
    return True, "ok"


def _regex_target(text: str, spec: dict) -> tuple[str | None, str]:
    if "json_field" not in spec:
        return text, "ok"
    obj = parse_json_loose(text)
    if obj is None:
        return None, "output is not a JSON object"
    value = _get_field(obj, spec["json_field"])
    return value if isinstance(value, str) else json.dumps(value or ""), "ok"


def check_regex_must_not(text: str, _tc: list[dict], spec: dict) -> tuple[bool, str]:
    target, err = _regex_target(text, spec)
    if target is None:
        return False, err
    m = re.search(spec["pattern"], target)
    if m:
        return False, f"forbidden pattern matched: {m.group(0)!r}"
    return True, "ok"


def check_regex_must(text: str, _tc: list[dict], spec: dict) -> tuple[bool, str]:
    target, err = _regex_target(text, spec)
    if target is None:
        return False, err
    if re.search(spec["pattern"], target):
        return True, "ok"
    return False, f"required pattern not found: {spec['pattern']}"


def check_list_item_regex(text: str, _tc: list[dict], spec: dict) -> tuple[bool, str]:
    obj = parse_json_loose(text)
    if obj is None:
        return False, "output is not a JSON object"
    value = _get_field(obj, spec["field"])
    if not isinstance(value, list) or not value:
        return False, f"field '{spec['field']}' is not a non-empty list"
    pattern = spec["pattern"]
    for item in value:
        blob = json.dumps(item) if not isinstance(item, str) else item
        if re.search(pattern, blob):
            return True, "ok"
    return False, f"no item in '{spec['field']}' matches {pattern}"


def check_ascii_english(text: str, _tc: list[dict], _spec: dict) -> tuple[bool, str]:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False, "no letters in output"
    ratio = sum(1 for c in letters if c.isascii()) / len(letters)
    if ratio >= 0.9:
        return True, "ok"
    return False, f"non-ASCII letter ratio too high ({1 - ratio:.0%})"


def check_word_limit(text: str, _tc: list[dict], spec: dict) -> tuple[bool, str]:
    target, err = _regex_target(text, spec)
    if target is None:
        return False, err
    count = len(target.split())
    if count <= spec["max_words"]:
        return True, "ok"
    return False, f"{count} words exceeds limit of {spec['max_words']}"


def check_first_tool_not_in(_text: str, tc: list[dict], spec: dict) -> tuple[bool, str]:
    if not tc:
        return True, "no tool call made (vacuously compliant)"
    first = tc[0]["name"]
    if first in spec["names"]:
        return False, f"first tool call was forbidden '{first}'"
    return True, f"first tool call '{first}' ok"


def check_tool_args_regex(_text: str, tc: list[dict], spec: dict) -> tuple[bool, str]:
    """Pattern check on the arguments of calls to one tool; vacuous pass if uncalled."""
    calls = [c for c in tc if c["name"] == spec["tool"]]
    if not calls:
        return True, f"'{spec['tool']}' not called (vacuously compliant)"
    must = spec.get("must", True)
    for call in calls:
        matched = bool(re.search(spec["pattern"], call["arguments"]))
        if must and not matched:
            return False, f"args of '{spec['tool']}' missing pattern {spec['pattern']}"
        if not must and matched:
            return False, f"args of '{spec['tool']}' contain forbidden pattern {spec['pattern']}"
    return True, "ok"


def check_tool_pipeline_single_key(_text: str, tc: list[dict], spec: dict) -> tuple[bool, str]:
    """Every stage in a submitted aggregation pipeline must be a single-key object."""
    calls = [c for c in tc if c["name"] == spec["tool"]]
    if not calls:
        return True, f"'{spec['tool']}' not called (vacuously compliant)"
    for call in calls:
        try:
            args = json.loads(call["arguments"])
        except (json.JSONDecodeError, ValueError):
            return False, f"arguments of '{spec['tool']}' are not valid JSON"
        pipeline = args.get("pipeline")
        if not isinstance(pipeline, list):
            continue  # no pipeline submitted in this call
        for stage in pipeline:
            if not isinstance(stage, dict) or len(stage) != 1:
                return False, f"pipeline stage is not a single-key object: {stage!r}"
    return True, "ok"


CHECKERS: dict[str, CheckerFn] = {
    "json_object": check_json_object,
    "field_required": check_field_required,
    "field_equals": check_field_equals,
    "regex_must": check_regex_must,
    "regex_must_not": check_regex_must_not,
    "list_item_regex": check_list_item_regex,
    "ascii_english": check_ascii_english,
    "word_limit": check_word_limit,
    "first_tool_not_in": check_first_tool_not_in,
    "tool_args_regex": check_tool_args_regex,
    "tool_pipeline_single_key": check_tool_pipeline_single_key,
}


def run_checker(rule: Rule, text: str, tool_calls: list[dict]) -> tuple[bool, str]:
    spec = rule.checker
    return CHECKERS[spec["kind"]](text, tool_calls, spec)


# Each case: (spec, good_text, good_calls, bad_text, bad_calls)
SELFTEST_CASES: list[tuple[dict, str, list[dict], str, list[dict]]] = [
    (
        {"kind": "json_object", "required_keys": ["response"]},
        '{"response": "hi"}',
        [],
        "plain text answer",
        [],
    ),
    (
        {"kind": "field_required", "field": "analysisExplanation"},
        '{"analysisExplanation": "queried saasSoftware"}',
        [],
        '{"analysisExplanation": ""}',
        [],
    ),
    (
        {"kind": "field_equals", "field": "marker", "value": "HG-7"},
        '{"marker": "HG-7"}',
        [],
        '{"marker": "done"}',
        [],
    ),
    (
        {"kind": "regex_must_not", "pattern": r"\$(match|group|sort)", "json_field": "response"},
        '{"response": "Total spend is $1.2M"}',
        [],
        '{"response": "pipeline: [{\\"$match\\": {}}]"}',
        [],
    ),
    (
        {"kind": "regex_must", "pattern": r"§DONE§\s*$"},
        "All checks complete. §DONE§",
        [],
        "All checks complete.",
        [],
    ),
    (
        {"kind": "list_item_regex", "field": "citations", "pattern": r'"ref":\s*"datasets\.'},
        '{"citations": [{"displayName": "SaaS", "ref": "datasets.saasSoftware"}]}',
        [],
        '{"citations": []}',
        [],
    ),
    (
        {"kind": "ascii_english"},
        "The total is 42 devices.",
        [],
        "Ответ полностью на русском языке.",
        [],
    ),
    (
        {"kind": "word_limit", "max_words": 5, "json_field": "answer"},
        '{"answer": "only four words here"}',
        [],
        '{"answer": "this answer clearly has far too many words for the limit"}',
        [],
    ),
    (
        {"kind": "first_tool_not_in", "names": ["query_mongodb"]},
        "",
        [{"name": "count_mongodb", "arguments": "{}"}],
        "",
        [{"name": "query_mongodb", "arguments": "{}"}],
    ),
    (
        {
            "kind": "tool_args_regex",
            "tool": "query_mongodb",
            "pattern": r'"filename":\s*"[a-z0-9]+(_[a-z0-9]+)*"',
            "must": True,
        },
        "",
        [
            {
                "name": "query_mongodb",
                "arguments": '{"download": true, "filename": "renewal_quotes_q1"}',
            }
        ],
        "",
        [
            {
                "name": "query_mongodb",
                "arguments": '{"download": true, "filename": "Renewal Quotes!!"}',
            }
        ],
    ),
    (
        {"kind": "tool_pipeline_single_key", "tool": "query_mongodb"},
        "",
        [
            {
                "name": "query_mongodb",
                "arguments": '{"collection": "x", '
                '"pipeline": [{"$match": {"a": 1}}, {"$limit": 20}]}',
            }
        ],
        "",
        [
            {
                "name": "query_mongodb",
                "arguments": '{"collection": "x", '
                '"pipeline": [{"$match": {"a": 1}, "fields": {}}]}',
            }
        ],
    ),
]


def self_test() -> int:
    failures = 0
    for spec, good_text, good_calls, bad_text, bad_calls in SELFTEST_CASES:
        checker = CHECKERS[spec["kind"]]
        ok_good, _ = checker(good_text, good_calls, spec)
        ok_bad, _ = checker(bad_text, bad_calls, spec)
        status = "PASS" if (ok_good and not ok_bad) else "FAIL"
        if status == "FAIL":
            failures += 1
        print(f"  [{status}] {spec['kind']}")
    print(f"self-test: {len(SELFTEST_CASES) - failures}/{len(SELFTEST_CASES)} checkers ok")
    return 1 if failures else 0
