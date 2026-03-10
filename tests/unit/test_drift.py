# tests/unit/test_drift.py
"""Unit tests for drift detection engine — T-0056."""
import pytest
from datetime import datetime, timezone

from core.drift import compute_drift, DriftReport, DriftEntry, DriftTrend
from core.models import Run, Result, Score


def make_run(run_id: str, evaluator: str, score_value: float) -> Run:
    return Run(
        run_id=run_id,
        dataset="my_dataset",
        target="http://agent",
        results=[
            Result(
                test_id="t1",
                evaluator=evaluator,
                score=Score(value=score_value),
                mode="threshold",
                min_score=0.7,
                duration_ms=10,
                trace_id=None,
            )
        ],
        started_at=datetime.now(timezone.utc),
        duration_ms=100,
        passed=score_value >= 0.7,
    )


def test_stable_scores_report_stable_trend():
    runs = [make_run(f"r{i}", "relevance", 0.9) for i in range(5)]
    report = compute_drift(runs, threshold=0.1)
    entry = next(e for e in report.entries if e.evaluator == "relevance")
    assert entry.trend == DriftTrend.STABLE


def test_score_drop_reports_down_trend():
    # 4 runs at 0.9, then last run at 0.5 — big drop
    runs = [make_run(f"r{i}", "relevance", 0.9) for i in range(4)]
    runs.append(make_run("r_latest", "relevance", 0.5))
    report = compute_drift(runs, threshold=0.1)
    entry = next(e for e in report.entries if e.evaluator == "relevance")
    assert entry.trend == DriftTrend.DOWN
    assert entry.current_score == pytest.approx(0.5)
    assert entry.baseline_score == pytest.approx(0.9)
    assert entry.delta == pytest.approx(-0.4, abs=0.01)


def test_score_improvement_reports_up_trend():
    runs = [make_run(f"r{i}", "relevance", 0.5) for i in range(4)]
    runs.append(make_run("r_latest", "relevance", 0.95))
    report = compute_drift(runs, threshold=0.1)
    entry = next(e for e in report.entries if e.evaluator == "relevance")
    assert entry.trend == DriftTrend.UP


def test_single_run_returns_no_baseline():
    runs = [make_run("r0", "relevance", 0.8)]
    report = compute_drift(runs, threshold=0.1)
    entry = next(e for e in report.entries if e.evaluator == "relevance")
    assert entry.baseline_score is None
    assert entry.trend == DriftTrend.STABLE


def test_multiple_evaluators_reported_independently():
    runs = []
    for i in range(5):
        r = Run(
            run_id=f"r{i}",
            dataset="ds",
            target="t",
            results=[
                Result(
                    test_id="t1",
                    evaluator="relevance",
                    score=Score(value=0.9),
                    mode="threshold",
                    min_score=0.7,
                    duration_ms=5,
                    trace_id=None,
                ),
                Result(
                    test_id="t1",
                    evaluator="safety",
                    score=Score(value=1.0 if i < 4 else 0.2),
                    mode="binary",
                    duration_ms=5,
                    trace_id=None,
                ),
            ],
            started_at=datetime.now(timezone.utc),
            duration_ms=50,
            passed=True,
        )
        runs.append(r)
    report = compute_drift(runs, threshold=0.1)
    evaluators = {e.evaluator for e in report.entries}
    assert "relevance" in evaluators
    assert "safety" in evaluators
    safety = next(e for e in report.entries if e.evaluator == "safety")
    assert safety.trend == DriftTrend.DOWN


def test_empty_runs_returns_empty_report():
    report = compute_drift([], threshold=0.1)
    assert report.entries == []


def test_delta_within_threshold_is_stable():
    # Drop of 0.05 when threshold is 0.1 → STABLE
    runs = [make_run(f"r{i}", "relevance", 0.9) for i in range(4)]
    runs.append(make_run("r_latest", "relevance", 0.85))
    report = compute_drift(runs, threshold=0.1)
    entry = next(e for e in report.entries if e.evaluator == "relevance")
    assert entry.trend == DriftTrend.STABLE
