# tests/unit/test_invocation_storage.py
"""Invocation + artifact + evaluator-result persistence round-trips."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from core.models import Artifact, EvaluatorResult, Invocation
from core.storage import (
    ArtifactRecord,
    EvaluatorResultRecord,
    SqliteStorage,
)
from sqlmodel import Session, select


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def storage(tmp_path):
    return SqliteStorage(db_url=f"sqlite:///{tmp_path}/test_inv.db")


def _artifact(kind: str = "request") -> Artifact:
    return Artifact(
        artifact_id=str(uuid.uuid4()),
        kind=kind,  # type: ignore[arg-type]
        content_type="application/json",
        storage_backend="inline",
        json_content='{"q": "hello"}',
        size_bytes=13,
        created_at=datetime.now(tz=timezone.utc),
    )


def _invocation(
    *,
    run_id: str | None = None,
    req_artifact_id: str | None = None,
    resp_artifact_id: str | None = None,
    contract_name: str | None = "my_contract",
    request_id: str | None = None,
    trace_id: str | None = None,
    status: str = "pass",
) -> Invocation:
    return Invocation(
        invocation_id=str(uuid.uuid4()),
        run_id=run_id,
        source="gateway_proxy",
        target="http://agent:8000",
        contract_name=contract_name,
        request_id=request_id or str(uuid.uuid4()),
        trace_id=trace_id or str(uuid.uuid4()),
        started_at=datetime.now(tz=timezone.utc),
        duration_ms=55,
        status=status,  # type: ignore[arg-type]
        request_artifact_id=req_artifact_id,
        response_artifact_id=resp_artifact_id,
    )


def _evaluator_result(invocation_id: str, evaluator: str = "contains") -> EvaluatorResult:
    return EvaluatorResult(
        evaluator_result_id=str(uuid.uuid4()),
        invocation_id=invocation_id,
        evaluator=evaluator,
        mode="binary",
        min_score=1.0,
        score_value=1.0,
        passed=True,
        reason="matched",
        duration_ms=10,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_round_trip_save_and_get_invocation(storage):
    """Every Invocation field survives save_invocation() -> get_invocation()."""
    req = _artifact("request")
    resp = _artifact("response")
    inv = _invocation(
        run_id="run-1",
        req_artifact_id=req.artifact_id,
        resp_artifact_id=resp.artifact_id,
    )
    inv.dataset = "refunds"
    inv.test_id = "t1"
    inv.provider = "openai"
    inv.model = "gpt-x"
    inv.model_version = "2026-01"
    inv.metadata_json = '{"category": "math"}'
    storage.save_invocation(inv, evaluator_results=[], artifacts=[req, resp])

    retrieved = storage.get_invocation(inv.invocation_id)
    assert retrieved is not None
    got = retrieved.model_dump(exclude={"started_at"})
    assert got == inv.model_dump(exclude={"started_at"})
    assert got["model"] == "gpt-x" and got["metadata_json"] == '{"category": "math"}'

    with Session(storage.engine) as session:
        stored = {r.artifact_id for r in session.exec(select(ArtifactRecord)).all()}
    assert stored == {req.artifact_id, resp.artifact_id}


def test_evaluator_result_rows_linked_to_invocation(storage):
    """EvaluatorResult rows persisted and linked to correct invocation."""
    inv = _invocation()
    er1 = _evaluator_result(inv.invocation_id, "contains")
    er2 = _evaluator_result(inv.invocation_id, "regex")

    storage.save_invocation(inv, evaluator_results=[er1, er2], artifacts=[])

    with Session(storage.engine) as session:
        stmt = select(EvaluatorResultRecord).where(
            EvaluatorResultRecord.invocation_id == inv.invocation_id
        )
        rows = session.exec(stmt).all()

    assert len(rows) == 2
    evaluators = {r.evaluator for r in rows}
    assert evaluators == {"contains", "regex"}
    for row in rows:
        assert row.invocation_id == inv.invocation_id


def test_invocation_with_run_id_none_persists_cleanly(storage):
    """Gateway-style invocation (run_id=None) persists without FK errors."""
    inv = _invocation(run_id=None)
    storage.save_invocation(inv, evaluator_results=[], artifacts=[])

    retrieved = storage.get_invocation(inv.invocation_id)
    assert retrieved is not None
    assert retrieved.run_id is None
    assert retrieved.invocation_id == inv.invocation_id


def test_get_invocation_missing_returns_none(storage):
    """get_invocation for unknown id returns None."""
    assert storage.get_invocation("nonexistent-id") is None
