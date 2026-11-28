# tests/unit/test_tool_event_capture.py
"""save_tool_calls: ToolCallEvent -> ToolCallRecord rows (step index, status)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from core.events import EventSink
from core.models import Invocation
from core.storage import SqliteStorage, ToolCallRecord
from sqlmodel import Session, select


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def storage(tmp_path):
    return SqliteStorage(db_url=f"sqlite:///{tmp_path}/test_tool_events.db")


@pytest.fixture
def invocation_id(storage) -> str:
    """Pre-insert minimal InvocationRecord to satisfy ToolCallRecord FK."""
    inv_id = str(uuid.uuid4())
    inv = Invocation(
        invocation_id=inv_id,
        source="gateway_proxy",
        target="http://agent",
        started_at=datetime.now(tz=timezone.utc),
        status="pass",
    )
    storage.save_invocation(inv, evaluator_results=[], artifacts=[])
    return inv_id


# ---------------------------------------------------------------------------
# save_tool_calls — persistence
# ---------------------------------------------------------------------------


def test_save_tool_calls_persists_rows_linked_to_invocation(storage, invocation_id):
    """save_tool_calls() writes ToolCallRecord rows FK'd to invocation_id."""
    sink = EventSink()
    sink.emit_tool_call("search", {"q": "hello"}, result="ok", duration_ms=12)
    sink.emit_tool_call("lookup", {"id": 42}, result=None, duration_ms=5)

    events = sink.drain()
    storage.save_tool_calls(invocation_id, events)

    with Session(storage.engine) as session:
        rows = session.exec(
            select(ToolCallRecord).where(ToolCallRecord.invocation_id == invocation_id)
        ).all()

    assert len(rows) == 2
    for row in rows:
        assert row.invocation_id == invocation_id


def test_save_tool_calls_step_index_assigned(storage, invocation_id):
    """step_index defaults to positional index when not set on event."""
    sink = EventSink()
    sink.emit_tool_call("tool0", {})
    sink.emit_tool_call("tool1", {})

    storage.save_tool_calls(invocation_id, sink.drain())

    with Session(storage.engine) as session:
        rows = session.exec(
            select(ToolCallRecord)
            .where(ToolCallRecord.invocation_id == invocation_id)
            .order_by(ToolCallRecord.step_index)  # type: ignore[arg-type]
        ).all()

    assert rows[0].step_index == 0
    assert rows[1].step_index == 1


def test_save_tool_calls_error_event_gets_error_status(storage, invocation_id):
    """An event with error set -> ToolCallRecord.status == 'error'."""
    sink = EventSink()
    sink.emit_tool_call("broken_tool", {}, error="timeout")

    storage.save_tool_calls(invocation_id, sink.drain())

    with Session(storage.engine) as session:
        rows = session.exec(
            select(ToolCallRecord).where(ToolCallRecord.invocation_id == invocation_id)
        ).all()

    assert rows[0].status == "error"
    assert rows[0].error_text == "timeout"


def test_save_tool_calls_success_event_gets_success_status(storage, invocation_id):
    """An event without error -> ToolCallRecord.status == 'success'."""
    sink = EventSink()
    sink.emit_tool_call("happy_tool", {}, result="ok")

    storage.save_tool_calls(invocation_id, sink.drain())

    with Session(storage.engine) as session:
        rows = session.exec(
            select(ToolCallRecord).where(ToolCallRecord.invocation_id == invocation_id)
        ).all()

    assert rows[0].status == "success"


# ---------------------------------------------------------------------------
# Runner: events a plugin emits are persisted with the invocation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_runner_persists_plugin_emitted_events_with_result_and_error(storage):
    import json

    from core.dataset import Dataset, EvaTestCase
    from core.models import Score
    from core.plugins import EvaPlugin, EvaSpec, make_manager
    from core.query import get_invocation_detail, list_invocations
    from core.runner import Runner

    class Emit(EvaPlugin):
        @EvaSpec.hook_impl
        def before_eval(self, test_id: str, context: dict) -> None:
            sink = context["event_sink"]
            sink.emit_tool_call("search", {"q": "eva"}, result={"hits": 2}, duration_ms=7)
            sink.emit_tool_call("lookup", {"id": 1}, error="not found")

    class Pass(EvaPlugin):
        @EvaSpec.hook_impl
        def run_eval(self, response: str, context: dict) -> Score:
            return Score(value=1.0)

    pm = make_manager()
    pm.register(Emit())
    pm.register(Pass())

    async def agent(prompt, target):
        return "done"

    ds = Dataset(
        name="d", target="http://fake",
        evaluators=[{"name": "always_pass", "mode": "binary"}],
        tests=[EvaTestCase(id="t1", input="go")],
    )
    await Runner(pm=pm, call_agent=agent, storage=storage).execute(ds)

    (inv,) = list_invocations(storage)
    detail = get_invocation_detail(storage, inv.invocation_id)
    calls = detail["tool_calls"]
    assert [(c.step_index, c.tool_name, c.status, c.error_text) for c in calls] == [
        (0, "search", "success", None),
        (1, "lookup", "error", "not found"),
    ]
    arts = {a.artifact_id: a for a in detail["artifacts"]}
    assert json.loads(arts[calls[0].args_artifact_id].json_content) == {"q": "eva"}
    assert json.loads(arts[calls[0].result_artifact_id].json_content) == {"hits": 2}
    assert calls[1].result_artifact_id is None
