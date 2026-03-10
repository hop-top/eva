# core/drift.py
"""Drift detection: compare evaluator scores across runs over time.

Given a list of Run objects (any order — sorted internally oldest→newest),
compute_drift:
  - Groups Result records by evaluator name.
  - The most recent run's score is the "current" score.
  - The mean of all earlier runs is the "baseline".
  - delta = current - baseline
  - trend = UP if delta > threshold, DOWN if delta < -threshold, else STABLE.
"""
from __future__ import annotations

from enum import Enum
from statistics import mean

from pydantic import BaseModel

from core.models import Run


class DriftTrend(str, Enum):
    UP = "up"
    DOWN = "down"
    STABLE = "stable"


class DriftEntry(BaseModel):
    evaluator: str
    baseline_score: float | None  # None when fewer than 2 runs exist
    current_score: float
    delta: float | None           # None when fewer than 2 runs exist
    trend: DriftTrend


class DriftReport(BaseModel):
    entries: list[DriftEntry]


def compute_drift(runs: list[Run], threshold: float = 0.1) -> DriftReport:
    """Compute drift report from a list of runs (any order — sorted internally).

    Args:
        runs: List of Run objects; any order; sorted by started_at internally.
        threshold: Score delta magnitude that triggers UP/DOWN trend.

    Returns:
        DriftReport with one DriftEntry per evaluator, sorted by evaluator name.
    """
    if not runs:
        return DriftReport(entries=[])

    # Sort oldest → newest by started_at
    sorted_runs = sorted(runs, key=lambda r: r.started_at)

    # Collect all scores per evaluator: {evaluator: [score, ...]} oldest first
    scores_by_evaluator: dict[str, list[float]] = {}
    for run in sorted_runs:
        for result in run.results:
            scores_by_evaluator.setdefault(result.evaluator, [])
            scores_by_evaluator[result.evaluator].append(result.score.value)

    entries: list[DriftEntry] = []
    for evaluator, scores in scores_by_evaluator.items():
        current = scores[-1]

        if len(scores) < 2:
            entries.append(
                DriftEntry(
                    evaluator=evaluator,
                    baseline_score=None,
                    current_score=current,
                    delta=None,
                    trend=DriftTrend.STABLE,
                )
            )
            continue

        baseline = mean(scores[:-1])
        delta = current - baseline

        if delta > threshold:
            trend = DriftTrend.UP
        elif delta < -threshold:
            trend = DriftTrend.DOWN
        else:
            trend = DriftTrend.STABLE

        entries.append(
            DriftEntry(
                evaluator=evaluator,
                baseline_score=round(baseline, 4),
                current_score=round(current, 4),
                delta=round(delta, 4),
                trend=trend,
            )
        )

    return DriftReport(entries=sorted(entries, key=lambda e: e.evaluator))
