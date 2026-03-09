# tests/unit/test_contract_diff.py
from pathlib import Path
import pytest

from core.models import Contract, EvaluatorRef
from core.contract_diff import diff_contracts, DiffReport, EvaluatorChange


def make_contract(evaluators: list[dict]) -> Contract:
    refs = [EvaluatorRef(**e) for e in evaluators]
    return Contract(name="test", provider="p", evaluators=refs)


def test_no_changes():
    a = make_contract([{"name": "contains", "min_score": 1.0}])
    b = make_contract([{"name": "contains", "min_score": 1.0}])
    report = diff_contracts(a, b)
    assert report.changes == []
    assert not report.has_regressions


def test_evaluator_removed_is_regression():
    a = make_contract([{"name": "contains"}, {"name": "no_pii"}])
    b = make_contract([{"name": "contains"}])
    report = diff_contracts(a, b)
    kinds = {c.name: c.kind for c in report.changes}
    assert kinds["no_pii"] == "removed"
    assert report.has_regressions


def test_evaluator_added_not_regression():
    a = make_contract([{"name": "contains"}])
    b = make_contract([{"name": "contains"}, {"name": "no_pii"}])
    report = diff_contracts(a, b)
    kinds = {c.name: c.kind for c in report.changes}
    assert kinds["no_pii"] == "added"
    assert not report.has_regressions


def test_threshold_raised_not_regression():
    a = make_contract([{"name": "regex", "mode": "threshold", "min_score": 0.7}])
    b = make_contract([{"name": "regex", "mode": "threshold", "min_score": 0.9}])
    report = diff_contracts(a, b)
    assert len(report.changes) == 1
    assert report.changes[0].kind == "threshold_raised"
    assert not report.has_regressions


def test_threshold_lowered_is_regression():
    a = make_contract([{"name": "regex", "mode": "threshold", "min_score": 0.9}])
    b = make_contract([{"name": "regex", "mode": "threshold", "min_score": 0.5}])
    report = diff_contracts(a, b)
    assert len(report.changes) == 1
    assert report.changes[0].kind == "threshold_lowered"
    assert report.has_regressions


def test_multiple_changes():
    a = make_contract([
        {"name": "contains"},
        {"name": "no_pii"},
        {"name": "regex", "mode": "threshold", "min_score": 0.8},
    ])
    b = make_contract([
        {"name": "contains"},
        {"name": "json_schema_valid"},
        {"name": "regex", "mode": "threshold", "min_score": 0.6},
    ])
    report = diff_contracts(a, b)
    kinds = {c.name: c.kind for c in report.changes}
    assert kinds["no_pii"] == "removed"
    assert kinds["json_schema_valid"] == "added"
    assert kinds["regex"] == "threshold_lowered"
    assert report.has_regressions


def test_empty_contracts():
    a = make_contract([])
    b = make_contract([])
    report = diff_contracts(a, b)
    assert report.changes == []
    assert not report.has_regressions
