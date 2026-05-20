# tests/e2e/test_json_path_evaluator.py
"""E2E tests: json_path evaluator (T-0319, US-045).

One test case per acceptance bullet in docs/stories/US-045-json-path-evaluator.md.
"""
from __future__ import annotations

from core.evaluators.json_path import JsonPathEvaluator
from core.models import Score


# AC1: invalid json -> fail.
def test_fails_on_invalid_json():
    ev = JsonPathEvaluator(path="a", expected=1)
    score = ev.run("not json at all")
    assert isinstance(score, Score)
    assert score.value == 0.0
    assert "invalid json" in (score.reason or "")


# AC2: eq comparator pass/fail.
def test_eq_passes_and_fails():
    ev = JsonPathEvaluator(path="status", comparator="eq", expected="ok")
    assert ev.run('{"status": "ok"}').value == 1.0
    assert ev.run('{"status": "bad"}').value == 0.0


# AC3: neq comparator.
def test_neq_passes_when_different():
    ev = JsonPathEvaluator(path="status", comparator="neq", expected="bad")
    assert ev.run('{"status": "ok"}').value == 1.0
    assert ev.run('{"status": "bad"}').value == 0.0


# AC4: gt comparator: numeric > vs non-numeric fail.
def test_gt_numeric_and_non_numeric():
    ev = JsonPathEvaluator(path="n", comparator="gt", expected=5)
    assert ev.run('{"n": 10}').value == 1.0
    assert ev.run('{"n": 3}').value == 0.0
    score = ev.run('{"n": "string"}')
    assert score.value == 0.0
    assert "not numeric" in (score.reason or "")


# AC5: lt comparator.
def test_lt_passes_and_fails():
    ev = JsonPathEvaluator(path="n", comparator="lt", expected=5)
    assert ev.run('{"n": 3}').value == 1.0
    assert ev.run('{"n": 7}').value == 0.0


# AC6: in comparator.
def test_in_passes_and_fails():
    ev = JsonPathEvaluator(
        path="status", comparator="in", expected=["ok", "ready"]
    )
    assert ev.run('{"status": "ok"}').value == 1.0
    assert ev.run('{"status": "broken"}').value == 0.0


# AC7: missing path -> fail with "path '...' not found".
def test_missing_path_fails():
    ev = JsonPathEvaluator(path="a.b.c", expected=1)
    score = ev.run('{"a": {"x": 1}}')
    assert score.value == 0.0
    assert "not found" in (score.reason or "")
    assert "a.b.c" in (score.reason or "")


# AC8: bracket-indexed arrays + dotted keys.
def test_bracket_indexed_array_walk():
    ev = JsonPathEvaluator(
        path="items[1].name", comparator="eq", expected="second"
    )
    body = '{"items": [{"name": "first"}, {"name": "second"}]}'
    assert ev.run(body).value == 1.0
