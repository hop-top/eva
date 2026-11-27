"""`field` scoping for the regex and contains evaluators."""
import json

import pytest

from core.evaluators.builtin import BUILTIN_EVALUATOR_FACTORIES
from core.evaluators.contains import ContainsEvaluator
from core.evaluators.regex_match import RegexEvaluator

PAYLOAD = json.dumps({"stdout": "Created task T-0042", "stderr": "TODO: warn", "code": 0})


def _regex(**kw):
    return RegexEvaluator(**kw)


def _contains(**kw):
    return ContainsEvaluator(**kw)


# --- regex ---------------------------------------------------------------

def test_regex_field_hit():
    assert _regex(pattern=r"T-\d{4}", field="stdout").run(PAYLOAD).value == 1.0


def test_regex_field_miss_pattern_exists_elsewhere():
    # 'TODO' is in stderr only; scoping to stdout must not see it
    s = _regex(pattern="TODO", field="stdout").run(PAYLOAD)
    assert s.value == 0.0
    assert s.reason


def test_regex_field_missing():
    s = _regex(pattern="x", field="nope").run(PAYLOAD)
    assert s.value == 0.0
    assert "nope" in s.reason


def test_regex_field_non_json_input():
    s = _regex(pattern="x", field="stdout").run("not json")
    assert s.value == 0.0
    assert "JSON" in s.reason


def test_regex_field_payload_not_object():
    s = _regex(pattern="x", field="stdout").run("[1, 2]")
    assert s.value == 0.0


def test_regex_field_non_string_value_scores_zero():
    s = _regex(pattern="0", field="code").run(PAYLOAD)
    assert s.value == 0.0
    assert "string" in s.reason


def test_regex_no_field_full_string_unchanged():
    assert _regex(pattern="TODO").run(PAYLOAD).value == 1.0
    assert _regex(pattern="TODO").run("plain text TODO").value == 1.0


# --- contains ------------------------------------------------------------

def test_contains_field_hit():
    assert _contains(substring="T-0042", field="stdout").run(PAYLOAD).value == 1.0


def test_contains_field_miss_substring_exists_elsewhere():
    s = _contains(substring="TODO", field="stdout").run(PAYLOAD)
    assert s.value == 0.0
    assert s.reason


def test_contains_field_case_insensitive():
    e = _contains(substring="CREATED", field="stdout", case_sensitive=False)
    assert e.run(PAYLOAD).value == 1.0


def test_contains_field_missing():
    s = _contains(substring="x", field="nope").run(PAYLOAD)
    assert s.value == 0.0
    assert "nope" in s.reason


def test_contains_field_non_json_input():
    s = _contains(substring="x", field="stdout").run("not json")
    assert s.value == 0.0
    assert "JSON" in s.reason


def test_contains_field_non_string_value_scores_zero():
    s = _contains(substring="0", field="code").run(PAYLOAD)
    assert s.value == 0.0
    assert "string" in s.reason


def test_contains_no_field_full_string_unchanged():
    assert _contains(substring="TODO").run(PAYLOAD).value == 1.0


# --- factory wiring ------------------------------------------------------

@pytest.mark.parametrize(
    "name,cfg",
    [
        ("regex", {"pattern": "TODO", "field": "stdout"}),
        ("contains", {"substring": "TODO", "field": "stdout"}),
    ],
)
def test_factory_passes_field(name, cfg):
    ev = BUILTIN_EVALUATOR_FACTORIES[name](cfg, None)
    assert ev.run(PAYLOAD).value == 0.0
