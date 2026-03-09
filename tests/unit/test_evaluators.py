# tests/unit/test_evaluators.py
import pytest
from core.evaluators.contains import ContainsEvaluator
from core.evaluators.regex_match import RegexEvaluator
from core.evaluators.json_schema_valid import JsonSchemaEvaluator
from core.evaluators.no_pii import NoPiiEvaluator


# --- contains ---
def test_contains_pass():
    e = ContainsEvaluator(substring="refund")
    score = e._run("Your refund has been processed")
    assert score.value == 1.0

def test_contains_fail():
    e = ContainsEvaluator(substring="refund")
    score = e._run("Sorry, we cannot help")
    assert score.value == 0.0
    assert "refund" in score.reason

def test_contains_case_insensitive():
    e = ContainsEvaluator(substring="refund", case_sensitive=False)
    score = e._run("Your REFUND is ready")
    assert score.value == 1.0


# --- regex ---
def test_regex_pass():
    e = RegexEvaluator(pattern=r"\d{3}-\d{4}")
    score = e._run("Call 555-1234 for help")
    assert score.value == 1.0

def test_regex_fail():
    e = RegexEvaluator(pattern=r"\d{3}-\d{4}")
    score = e._run("No phone number here")
    assert score.value == 0.0


# --- json_schema_valid ---
def test_json_schema_valid_pass():
    e = JsonSchemaEvaluator(schema={"type": "object", "required": ["price"]})
    score = e._run('{"price": 42}')
    assert score.value == 1.0

def test_json_schema_valid_fail_not_json():
    e = JsonSchemaEvaluator(schema={"type": "object"})
    score = e._run("not json at all")
    assert score.value == 0.0
    assert score.reason is not None

def test_json_schema_valid_fail_schema():
    e = JsonSchemaEvaluator(schema={"type": "object", "required": ["price"]})
    score = e._run('{"discount": 10}')
    assert score.value == 0.0


# --- no_pii ---
def test_no_pii_pass():
    e = NoPiiEvaluator()
    score = e._run("Your order has been processed successfully")
    assert score.value == 1.0

def test_no_pii_fail_email():
    e = NoPiiEvaluator()
    score = e._run("Contact john@example.com for help")
    assert score.value == 0.0
    assert score.reason is not None

def test_no_pii_fail_ssn():
    e = NoPiiEvaluator()
    score = e._run("SSN: 123-45-6789")
    assert score.value == 0.0
