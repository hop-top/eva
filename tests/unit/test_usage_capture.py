# tests/unit/test_usage_capture.py
"""T-0119: Usage record persistence — save_usage_record / get_usage_records."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from core.costing import estimate_cost
from core.llm import LLMCompletion
from core.models import Invocation, UsageRecord
from core.storage import SqliteStorage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def storage(tmp_path):
    return SqliteStorage(db_url=f"sqlite:///{tmp_path}/test_usage.db")


@pytest.fixture
def invocation_id(storage) -> str:
    """Pre-insert a minimal InvocationRecord so FK constraint is satisfied."""
    inv_id = str(uuid.uuid4())
    inv = Invocation(
        invocation_id=inv_id,
        source="offline_run",
        target="http://localhost",
        started_at=datetime.now(tz=timezone.utc),
        status="pass",
    )
    storage.save_invocation(inv, evaluator_results=[], artifacts=[])
    return inv_id


def _make_usage(invocation_id: str, scope: str = "agent", **overrides) -> UsageRecord:
    defaults = dict(
        usage_id=str(uuid.uuid4()),
        invocation_id=invocation_id,
        scope=scope,
        provider="openai",
        model="gpt-4o-mini",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        estimated_cost_usd=0.00004,
    )
    defaults.update(overrides)
    return UsageRecord(**defaults)


# ---------------------------------------------------------------------------
# Token counts / provider / model extracted from LLMCompletion
# ---------------------------------------------------------------------------


def test_fields_extracted_from_llm_completion():
    """Token counts, provider, model accessible on LLMCompletion."""
    completion = LLMCompletion(
        content="hello",
        provider="anthropic",
        model="claude-3-5-haiku",
        usage={"prompt_tokens": 200, "completion_tokens": 80, "total_tokens": 280},
        raw_response=None,
    )
    assert completion.provider == "anthropic"
    assert completion.model == "claude-3-5-haiku"
    assert completion.usage["prompt_tokens"] == 200
    assert completion.usage["completion_tokens"] == 80
    assert completion.usage["total_tokens"] == 280


def test_estimate_cost_from_completion_fields():
    """estimate_cost() called with provider/model from LLMCompletion returns float."""
    completion = LLMCompletion(
        content="hi",
        provider="openai",
        model="gpt-4o-mini",
        usage={"prompt_tokens": 1000, "completion_tokens": 500},
        raw_response=None,
    )
    cost = estimate_cost(
        provider=completion.provider or "",
        model=completion.model,
        prompt_tokens=completion.usage.get("prompt_tokens", 0),
        completion_tokens=completion.usage.get("completion_tokens", 0),
    )
    assert cost is not None
    assert cost > 0.0


# ---------------------------------------------------------------------------
# Round-trip: save_usage_record / get_usage_records
# ---------------------------------------------------------------------------


def test_save_and_retrieve_usage_record(storage, invocation_id):
    usage = _make_usage(invocation_id)
    storage.save_usage_record(usage)

    records = storage.get_usage_records(invocation_id)
    assert len(records) == 1
    r = records[0]
    assert r.usage_id == usage.usage_id
    assert r.invocation_id == invocation_id
    assert r.provider == "openai"
    assert r.model == "gpt-4o-mini"
    assert r.prompt_tokens == 100
    assert r.completion_tokens == 50
    assert r.total_tokens == 150
    assert r.estimated_cost_usd == pytest.approx(0.00004)


def test_multiple_records_for_same_invocation(storage, invocation_id):
    r1 = _make_usage(invocation_id, scope="agent")
    r2 = _make_usage(invocation_id, scope="evaluator_judge")
    storage.save_usage_record(r1)
    storage.save_usage_record(r2)

    records = storage.get_usage_records(invocation_id)
    assert len(records) == 2
    scopes = {r.scope for r in records}
    assert scopes == {"agent", "evaluator_judge"}


def test_get_usage_records_empty_for_unknown_invocation(storage):
    records = storage.get_usage_records("nonexistent-invocation-id")
    assert records == []


def test_upsert_idempotent(storage, invocation_id):
    """save_usage_record is idempotent (merge on same usage_id)."""
    usage = _make_usage(invocation_id, prompt_tokens=10)
    storage.save_usage_record(usage)

    usage_updated = _make_usage(
        invocation_id,
        prompt_tokens=999,
    )
    # Force same usage_id to simulate upsert
    object.__setattr__(usage_updated, "usage_id", usage.usage_id)
    storage.save_usage_record(usage_updated)

    records = storage.get_usage_records(invocation_id)
    assert len(records) == 1
    assert records[0].prompt_tokens == 999


# ---------------------------------------------------------------------------
# scope field correctness
# ---------------------------------------------------------------------------


def test_scope_agent(storage, invocation_id):
    usage = _make_usage(invocation_id, scope="agent")
    storage.save_usage_record(usage)
    records = storage.get_usage_records(invocation_id)
    assert records[0].scope == "agent"


def test_scope_evaluator_judge(storage, invocation_id):
    usage = _make_usage(invocation_id, scope="evaluator_judge")
    storage.save_usage_record(usage)
    records = storage.get_usage_records(invocation_id)
    assert records[0].scope == "evaluator_judge"


def test_scope_preserved_independently(storage, invocation_id):
    """Two records with different scopes remain independent after retrieval."""
    agent_usage = _make_usage(invocation_id, scope="agent")
    judge_usage = _make_usage(invocation_id, scope="evaluator_judge")
    storage.save_usage_record(agent_usage)
    storage.save_usage_record(judge_usage)

    records = storage.get_usage_records(invocation_id)
    scope_map = {r.usage_id: r.scope for r in records}
    assert scope_map[agent_usage.usage_id] == "agent"
    assert scope_map[judge_usage.usage_id] == "evaluator_judge"
