# tests/unit/test_evaluators.py
import pytest
from core.evaluators.contains import ContainsEvaluator
from core.evaluators.regex_match import RegexEvaluator
from core.evaluators.json_schema_valid import JsonSchemaEvaluator
from core.evaluators.no_pii import NoPiiEvaluator


# --- contains ---
def test_contains_pass():
    e = ContainsEvaluator(substring="refund")
    score = e.run("Your refund has been processed")
    assert score.value == 1.0

def test_contains_fail():
    e = ContainsEvaluator(substring="refund")
    score = e.run("Sorry, we cannot help")
    assert score.value == 0.0
    assert "refund" in score.reason

def test_contains_case_insensitive():
    e = ContainsEvaluator(substring="refund", case_sensitive=False)
    score = e.run("Your REFUND is ready")
    assert score.value == 1.0


# --- regex ---
def test_regex_pass():
    e = RegexEvaluator(pattern=r"\d{3}-\d{4}")
    score = e.run("Call 555-1234 for help")
    assert score.value == 1.0

def test_regex_fail():
    e = RegexEvaluator(pattern=r"\d{3}-\d{4}")
    score = e.run("No phone number here")
    assert score.value == 0.0


# --- json_schema_valid ---
def test_json_schema_valid_pass():
    e = JsonSchemaEvaluator(schema={"type": "object", "required": ["price"]})
    score = e.run('{"price": 42}')
    assert score.value == 1.0

def test_json_schema_valid_fail_not_json():
    e = JsonSchemaEvaluator(schema={"type": "object"})
    score = e.run("not json at all")
    assert score.value == 0.0
    assert score.reason is not None

def test_json_schema_valid_fail_schema():
    e = JsonSchemaEvaluator(schema={"type": "object", "required": ["price"]})
    score = e.run('{"discount": 10}')
    assert score.value == 0.0


# --- no_pii ---
def test_no_pii_pass():
    e = NoPiiEvaluator()
    score = e.run("Your order has been processed successfully")
    assert score.value == 1.0

def test_no_pii_fail_email():
    e = NoPiiEvaluator()
    score = e.run("Contact john@example.com for help")
    assert score.value == 0.0
    assert score.reason is not None

def test_no_pii_fail_ssn():
    e = NoPiiEvaluator()
    score = e.run("SSN: 123-45-6789")
    assert score.value == 0.0


# --- deprecated _run alias coverage (T-0262) ---
# `_run` is kept as a backward-compat alias for run() — external plugins
# may still call it. Drop in v0.2.0.
@pytest.mark.parametrize(
    "evaluator",
    [
        ContainsEvaluator(substring="ok"),
        RegexEvaluator(pattern=r"\d+"),
        JsonSchemaEvaluator(schema={"type": "object"}),
        NoPiiEvaluator(),
    ],
)
def test_legacy_underscore_run_alias(evaluator):
    # Bound methods compare equal when they wrap the same function;
    # `is` would fail because each attribute access produces a fresh wrapper.
    assert evaluator._run == evaluator.run
    assert type(evaluator)._run is type(evaluator).run
