# tests/server/test_gateway_tool_events.py
"""Gateway requests with emitted tool events persist ToolCall rows."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport

from core.events import EventSink
from core.storage import SqliteStorage, InvocationRecord, ToolCallRecord
from server.app import create_app
from server.gateway import routes as gateway_routes
from sqlmodel import Session, select


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def storage(tmp_path):
    return SqliteStorage(db_url=f"sqlite:///{tmp_path}/test_gw_tool_events.db")


@pytest.fixture
def app_with_storage(storage):
    """App instance wired with a real SqliteStorage."""
    _app = create_app()
    gateway_routes.set_storage(storage)
    yield _app
    gateway_routes.set_storage(None)


def _proxy_response(text: str, status: int = 200):
    from server.gateway.proxy import ProxyResponse
    return ProxyResponse(status_code=status, text=text, headers={})


def _emit_tool_events_on_sink(sink: EventSink) -> None:
    """Helper: emit two tool calls on the given sink."""
    sink.emit_tool_call("web_search", {"query": "eva testing"}, result="results", duration_ms=80)
    sink.emit_tool_call("db_lookup", {"id": 99}, result=None, error="not found", duration_ms=5)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_events_emitted_by_agent_persist_as_tool_call_rows(
    app_with_storage, storage
):
    """Tool events emitted into the gateway sink are persisted as ToolCallRecord rows."""
    # Intercept EventSink creation inside the route to emit events
    original_sink_class = gateway_routes.EventSink

    class _InstrumentedSink(original_sink_class):
        def __init__(self):
            super().__init__()
            _emit_tool_events_on_sink(self)

    with patch("server.gateway.routes.EventSink", _InstrumentedSink):
        with patch("server.gateway.routes.forward_request", new_callable=AsyncMock) as mock_fwd:
            mock_fwd.return_value = _proxy_response('{"answer": "ok"}')
            async with AsyncClient(
                transport=ASGITransport(app=app_with_storage), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/v1/proxy",
                    json={"target": "http://agent/v1", "body": {}, "evaluators": []},
                )

    assert resp.status_code == 200

    with Session(storage.engine) as session:
        rows = session.exec(select(ToolCallRecord)).all()

    assert len(rows) == 2
    tool_names = {r.tool_name for r in rows}
    assert "web_search" in tool_names
    assert "db_lookup" in tool_names


@pytest.mark.asyncio
async def test_tool_calls_linked_to_correct_invocation(app_with_storage, storage):
    """ToolCallRecord.invocation_id matches the persisted InvocationRecord."""
    original_sink_class = gateway_routes.EventSink

    class _SinkWithEvents(original_sink_class):
        def __init__(self):
            super().__init__()
            self.emit_tool_call("my_tool", {"x": 1}, result="done", duration_ms=20)

    with patch("server.gateway.routes.EventSink", _SinkWithEvents):
        with patch("server.gateway.routes.forward_request", new_callable=AsyncMock) as mock_fwd:
            mock_fwd.return_value = _proxy_response('{"ok": true}')
            async with AsyncClient(
                transport=ASGITransport(app=app_with_storage), base_url="http://test"
            ) as client:
                await client.post(
                    "/v1/proxy",
                    json={"target": "http://agent/v1", "body": {}, "evaluators": []},
                )

    with Session(storage.engine) as session:
        inv_rows = session.exec(select(InvocationRecord)).all()
        tc_rows = session.exec(select(ToolCallRecord)).all()

    assert len(inv_rows) == 1
    assert len(tc_rows) == 1
    assert tc_rows[0].invocation_id == inv_rows[0].invocation_id


@pytest.mark.asyncio
async def test_tool_calls_filterable_by_status(app_with_storage, storage):
    """ToolCallRecord rows are filterable by status (success vs error)."""
    original_sink_class = gateway_routes.EventSink

    class _MixedStatusSink(original_sink_class):
        def __init__(self):
            super().__init__()
            self.emit_tool_call("good_tool", {}, result="ok", duration_ms=1)
            self.emit_tool_call("bad_tool", {}, error="failed", duration_ms=2)

    with patch("server.gateway.routes.EventSink", _MixedStatusSink):
        with patch("server.gateway.routes.forward_request", new_callable=AsyncMock) as mock_fwd:
            mock_fwd.return_value = _proxy_response('{"ok": 1}')
            async with AsyncClient(
                transport=ASGITransport(app=app_with_storage), base_url="http://test"
            ) as client:
                await client.post(
                    "/v1/proxy",
                    json={"target": "http://agent/v1", "body": {}, "evaluators": []},
                )

    with Session(storage.engine) as session:
        success_rows = session.exec(
            select(ToolCallRecord).where(ToolCallRecord.status == "success")
        ).all()
        error_rows = session.exec(
            select(ToolCallRecord).where(ToolCallRecord.status == "error")
        ).all()

    assert len(success_rows) == 1
    assert success_rows[0].tool_name == "good_tool"
    assert len(error_rows) == 1
    assert error_rows[0].tool_name == "bad_tool"


@pytest.mark.asyncio
async def test_no_tool_events_means_no_tool_call_rows(app_with_storage, storage):
    """When no tool events are emitted, no ToolCallRecord rows are created."""
    with patch("server.gateway.routes.forward_request", new_callable=AsyncMock) as mock_fwd:
        mock_fwd.return_value = _proxy_response('{"ok": true}')
        async with AsyncClient(
            transport=ASGITransport(app=app_with_storage), base_url="http://test"
        ) as client:
            await client.post(
                "/v1/proxy",
                json={"target": "http://agent/v1", "body": {}, "evaluators": []},
            )

    with Session(storage.engine) as session:
        rows = session.exec(select(ToolCallRecord)).all()

    assert rows == []
