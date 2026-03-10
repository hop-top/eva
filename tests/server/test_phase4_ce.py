# tests/server/test_phase4_ce.py
"""Phase 4 CE integration smoke test — T-0058 (CE portion).

Validates:
- Auth middleware: valid key passes, missing key → 401
- Drift detection: mock 20 runs → DriftReport shape correct
- /.well-known/agent.json accessible without auth (exempt path)
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient, ASGITransport

from server.app import create_app
from server.auth import ApiKeyMiddleware
from core.drift import compute_drift, DriftReport, DriftTrend
from core.models import Run, Result, Score


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _make_run(run_id: str, started_at: datetime, score_value: float) -> Run:
    """Build a minimal Run with one 'accuracy' evaluator result."""
    result = Result(
        test_id=f"t_{run_id}",
        evaluator="accuracy",
        score=Score(value=score_value),
        mode="threshold",
        min_score=0.7,
        duration_ms=100,
    )
    return Run(
        run_id=run_id,
        dataset="smoke_dataset",
        target="http://agent/v1",
        results=[result],
        started_at=started_at,
        duration_ms=500,
    )


# --------------------------------------------------------------------------- #
# Auth middleware smoke tests                                                  #
# --------------------------------------------------------------------------- #


@pytest.fixture
def authed_app():
    return create_app(middleware_factories=[ApiKeyMiddleware])


@pytest.mark.asyncio
async def test_auth_missing_key_returns_401(authed_app):
    async with AsyncClient(
        transport=ASGITransport(app=authed_app), base_url="http://test"
    ) as client:
        resp = await client.post("/v1/proxy", json={"input": "hello"})
    assert resp.status_code == 401
    assert "X-Eva-Key" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_auth_valid_key_passes(authed_app, valid_api_key, mock_state_valid_key):
    async with AsyncClient(
        transport=ASGITransport(app=authed_app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/v1/proxy",
            json={"input": "hello", "target": "http://example.com"},
            headers={"X-Eva-Key": valid_api_key},
        )
    # Auth passed — downstream may fail but not 401
    assert resp.status_code != 401


@pytest.mark.asyncio
async def test_well_known_agent_json_accessible_without_auth(authed_app):
    """/.well-known/agent.json must be exempt from auth — returns 200 or 404, never 401."""
    async with AsyncClient(
        transport=ASGITransport(app=authed_app), base_url="http://test"
    ) as client:
        resp = await client.get("/.well-known/agent.json")
    assert resp.status_code != 401


@pytest.mark.asyncio
async def test_health_exempt_from_auth(authed_app):
    async with AsyncClient(
        transport=ASGITransport(app=authed_app), base_url="http://test"
    ) as client:
        resp = await client.get("/health")
    assert resp.status_code == 200


# --------------------------------------------------------------------------- #
# Drift detection smoke tests                                                  #
# --------------------------------------------------------------------------- #


def test_drift_report_shape_with_20_runs():
    """compute_drift on 20 runs must return a DriftReport with correct structure."""
    base_time = datetime(2026, 3, 1, tzinfo=timezone.utc)
    # 19 historical runs at score 0.9, then 1 degraded run at 0.5
    runs = [
        _make_run(f"run_{i:03d}", base_time + timedelta(hours=i), 0.9)
        for i in range(19)
    ]
    runs.append(_make_run("run_019", base_time + timedelta(hours=19), 0.5))

    report = compute_drift(runs, threshold=0.1)

    assert isinstance(report, DriftReport)
    assert len(report.entries) == 1  # one evaluator: "accuracy"

    entry = report.entries[0]
    assert entry.evaluator == "accuracy"
    assert entry.current_score == pytest.approx(0.5)
    assert entry.baseline_score is not None
    assert entry.delta is not None
    # delta should be negative (degraded) and exceed threshold
    assert entry.delta < -0.1
    assert entry.trend == DriftTrend.DOWN


def test_drift_report_stable_with_consistent_scores():
    """All identical scores → STABLE trend."""
    base_time = datetime(2026, 3, 1, tzinfo=timezone.utc)
    runs = [
        _make_run(f"run_{i:03d}", base_time + timedelta(hours=i), 0.85)
        for i in range(10)
    ]
    report = compute_drift(runs, threshold=0.1)
    assert report.entries[0].trend == DriftTrend.STABLE


def test_drift_report_empty_runs():
    """No runs → empty DriftReport."""
    report = compute_drift([])
    assert report.entries == []


def test_drift_report_single_run_no_baseline():
    """Single run → current_score set, baseline/delta None, trend STABLE."""
    run = _make_run("run_000", datetime(2026, 3, 1, tzinfo=timezone.utc), 0.8)
    report = compute_drift([run])
    entry = report.entries[0]
    assert entry.baseline_score is None
    assert entry.delta is None
    assert entry.trend == DriftTrend.STABLE
