# tests/unit/test_flow_exec_evaluators.py
"""Tests for Tier-1 flow-exec evaluators: status_code, exit_code, equals."""
import json

import pytest

from core.evaluators import EVALUATOR_REGISTRY, ExitCodeEvaluator, StatusCodeEvaluator
from core.evaluators.equals import EqualsEvaluator
from core.evaluators.status_code import StatusCodeEvaluator as DirectStatusCode


def _payload(**fields) -> str:
    return json.dumps(fields)


# --- status_code: happy path ---
def test_status_code_pass_exit_code_field():
    e = StatusCodeEvaluator(step="cli-version", expected=0)
    score = e._run(_payload(exit_code=0, stdout="v1.0", stderr=""))
    assert score.value == 1.0


def test_status_code_pass_status_code_field():
    e = StatusCodeEvaluator(step="http-call", expected=200)
    score = e._run(_payload(status_code=200, body="{}"))
    assert score.value == 1.0


def test_status_code_pass_expected_in_set():
    e = StatusCodeEvaluator(step="cli-version", expected_in=[0, 2])
    score = e._run(_payload(exit_code=2, stdout="", stderr="warn"))
    assert score.value == 1.0


# --- status_code: failure cases ---
def test_status_code_fail_mismatch():
    e = StatusCodeEvaluator(step="cli-version", expected=0)
    score = e._run(_payload(exit_code=1, stdout="", stderr="boom"))
    assert score.value == 0.0
    assert "expected 0" in score.reason
    assert "got 1" in score.reason


def test_status_code_fail_not_in_set():
    e = StatusCodeEvaluator(step="cli-version", expected_in=[0, 2])
    score = e._run(_payload(exit_code=127))
    assert score.value == 0.0
    assert "127" in score.reason


def test_status_code_fail_no_field():
    e = StatusCodeEvaluator(step="cli-version", expected=0)
    score = e._run(_payload(stdout="v1.0", stderr=""))
    assert score.value == 0.0
    assert "no integer" in score.reason


# --- status_code: malformed input ---
def test_status_code_invalid_json():
    e = StatusCodeEvaluator(step="cli-version", expected=0)
    score = e._run("not json at all")
    assert score.value == 0.0
    assert "invalid JSON" in score.reason


def test_status_code_payload_not_object():
    e = StatusCodeEvaluator(step="cli-version", expected=0)
    score = e._run("[1, 2, 3]")
    assert score.value == 0.0
    assert "not a JSON object" in score.reason


def test_status_code_field_not_int():
    e = StatusCodeEvaluator(step="cli-version", expected=0)
    score = e._run(_payload(exit_code="zero"))
    assert score.value == 0.0


def test_status_code_field_bool_rejected():
    # bool is a subclass of int in Python — explicitly reject.
    e = StatusCodeEvaluator(step="cli-version", expected=0)
    score = e._run(_payload(exit_code=False))
    assert score.value == 0.0


# --- status_code: config validation ---
def test_status_code_requires_expected_or_expected_in():
    with pytest.raises(ValueError, match="expected"):
        StatusCodeEvaluator(step="cli-version")


def test_status_code_rejects_both_expected_and_expected_in():
    with pytest.raises(ValueError, match="mutually exclusive"):
        StatusCodeEvaluator(step="cli-version", expected=0, expected_in=[0, 1])


# --- exit_code alias ---
def test_exit_code_is_status_code_alias():
    assert ExitCodeEvaluator is StatusCodeEvaluator


def test_exit_code_alias_works_end_to_end():
    e = ExitCodeEvaluator(step="cli-version", expected=0)
    score = e._run(_payload(exit_code=0))
    assert score.value == 1.0


def test_registry_has_both_names():
    assert "status_code" in EVALUATOR_REGISTRY
    assert "exit_code" in EVALUATOR_REGISTRY
    assert EVALUATOR_REGISTRY["status_code"] is EVALUATOR_REGISTRY["exit_code"]
    assert EVALUATOR_REGISTRY["status_code"] is DirectStatusCode


# --- equals: happy path ---
def test_equals_string_pass():
    e = EqualsEvaluator(field="log_level", expected="info")
    score = e._run(_payload(log_level="info", verbose=False))
    assert score.value == 1.0


def test_equals_int_pass():
    e = EqualsEvaluator(field="count", expected=42)
    score = e._run(_payload(count=42))
    assert score.value == 1.0


def test_equals_bool_pass():
    e = EqualsEvaluator(field="ok", expected=True)
    score = e._run(_payload(ok=True))
    assert score.value == 1.0


def test_equals_list_pass():
    e = EqualsEvaluator(field="tags", expected=["a", "b"])
    score = e._run(_payload(tags=["a", "b"]))
    assert score.value == 1.0


def test_equals_dict_pass():
    e = EqualsEvaluator(field="meta", expected={"k": 1})
    score = e._run(_payload(meta={"k": 1}))
    assert score.value == 1.0


def test_equals_int_float_cross_compare():
    # JSON numbers may decode as int or float — equality across the
    # numeric tower is intentional.
    e = EqualsEvaluator(field="ratio", expected=1.0)
    score = e._run(_payload(ratio=1))
    assert score.value == 1.0


# --- equals: failure cases ---
def test_equals_value_mismatch():
    e = EqualsEvaluator(field="log_level", expected="info")
    score = e._run(_payload(log_level="debug"))
    assert score.value == 0.0
    assert "log_level" in score.reason
    assert "debug" in score.reason


def test_equals_field_missing():
    e = EqualsEvaluator(field="log_level", expected="info")
    score = e._run(_payload(other="value"))
    assert score.value == 0.0
    assert "missing" in score.reason


def test_equals_type_mismatch():
    # bool vs int is the classic Python footgun — keep them distinct.
    e = EqualsEvaluator(field="ok", expected=True)
    score = e._run(_payload(ok=1))
    assert score.value == 0.0
    assert "type mismatch" in score.reason


def test_equals_string_vs_int_type_mismatch():
    e = EqualsEvaluator(field="count", expected=42)
    score = e._run(_payload(count="42"))
    assert score.value == 0.0
    assert "type mismatch" in score.reason


# --- equals: malformed input ---
def test_equals_invalid_json():
    e = EqualsEvaluator(field="log_level", expected="info")
    score = e._run("garbage")
    assert score.value == 0.0
    assert "invalid JSON" in score.reason


def test_equals_payload_not_object():
    e = EqualsEvaluator(field="log_level", expected="info")
    score = e._run('"just a string"')
    assert score.value == 0.0
    assert "not a JSON object" in score.reason


# --- equals: config validation ---
def test_equals_requires_field():
    with pytest.raises(ValueError, match="field"):
        EqualsEvaluator(expected="info")


def test_equals_requires_expected():
    with pytest.raises(ValueError, match="expected"):
        EqualsEvaluator(field="log_level")


def test_equals_accepts_none_as_expected():
    e = EqualsEvaluator(field="optional", expected=None)
    score = e._run(_payload(optional=None))
    assert score.value == 1.0


def test_equals_in_registry():
    assert EVALUATOR_REGISTRY["equals"] is EqualsEvaluator
