# tests/server/test_gateway_persistence.py
"""Gateway requests persist Invocation records queryable after completion."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport

from core.storage import SqliteStorage, InvocationRecord
from server.app import create_app
from server.gateway import routes as gateway_routes
from sqlmodel import Session, select


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def storage(tmp_path):
    return SqliteStorage(db_url=f"sqlite:///{tmp_path}/test_gw_persist.db")


@pytest.fixture
def app_with_storage(storage):
    """App instance wired with a real SqliteStorage."""
    _app = create_app()
    gateway_routes.set_storage(storage)
    yield _app
    # teardown: detach storage so other tests are unaffected
    gateway_routes.set_storage(None)


def _proxy_response(text: str, status: int = 200):
    from server.gateway.proxy import ProxyResponse
    return ProxyResponse(status_code=status, text=text, headers={})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gateway_pass_persists_invocation(app_with_storage, storage):
    """Pass path: invocation is queryable after successful proxy request."""
    with patch("server.gateway.routes.forward_request", new_callable=AsyncMock) as mock_fwd:
        mock_fwd.return_value = _proxy_response('{"answer": "ok"}')
        async with AsyncClient(
            transport=ASGITransport(app=app_with_storage), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/v1/proxy",
                json={"target": "http://agent/chat", "body": {"q": "hello"}, "evaluators": []},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["eva_status"] == "pass"

    # Verify storage has exactly one invocation
    with Session(storage.engine) as session:
        rows = session.exec(select(InvocationRecord)).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.status == "pass"
    assert row.source == "gateway_proxy"
    assert row.target == "http://agent/chat"
    assert row.run_id is None  # gateway traffic is not part of a dataset run


@pytest.mark.asyncio
async def test_gateway_fail_persists_invocation(app_with_storage, storage):
    """Fail path: invocation is persisted even when evaluator rejects the response."""
    with patch("server.gateway.routes.forward_request", new_callable=AsyncMock) as mock_fwd:
        mock_fwd.return_value = _proxy_response('{"answer": "bad"}')
        async with AsyncClient(
            transport=ASGITransport(app=app_with_storage), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/v1/proxy",
                json={
                    "target": "http://agent/chat",
                    "body": {"q": "hi"},
                    "evaluators": [
                        {"name": "contains", "mode": "binary", "config": {"substring": "REQUIRED"}}
                    ],
                    "max_retries": 0,
                },
            )

    # 422 contract violation — but invocation must still be persisted
    assert resp.status_code == 422

    with Session(storage.engine) as session:
        rows = session.exec(select(InvocationRecord)).all()
    assert len(rows) == 1
    assert rows[0].status == "fail"


@pytest.mark.asyncio
async def test_persisted_invocation_has_contract_name_request_id_trace_id(
    app_with_storage, storage
):
    """Persisted record carries contract_name, request_id, trace_id."""
    with patch("server.gateway.routes.forward_request", new_callable=AsyncMock) as mock_fwd:
        mock_fwd.return_value = _proxy_response('{"ok": true}')
        async with AsyncClient(
            transport=ASGITransport(app=app_with_storage), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/v1/proxy",
                json={"target": "http://agent/v1", "body": {}, "evaluators": []},
            )

    assert resp.status_code == 200
    resp_data = resp.json()

    with Session(storage.engine) as session:
        rows = session.exec(select(InvocationRecord)).all()
    assert len(rows) == 1
    row = rows[0]

    # contract_name defaults to "inline" for /v1/proxy
    assert row.contract_name == "inline"
    # request_id and trace_id echoed in response and in the DB row
    assert row.request_id == resp_data["request_id"]
    # trace_id echoed in response; may be None without OTEL
    assert row.trace_id == resp_data.get("trace_id")


@pytest.mark.asyncio
async def test_multiple_requests_each_create_separate_invocation(app_with_storage, storage):
    """Two gateway requests create two separate InvocationRecord rows."""
    with patch("server.gateway.routes.forward_request", new_callable=AsyncMock) as mock_fwd:
        mock_fwd.return_value = _proxy_response('{"r": 1}')
        async with AsyncClient(
            transport=ASGITransport(app=app_with_storage), base_url="http://test"
        ) as client:
            await client.post(
                "/v1/proxy",
                json={"target": "http://agent/v1", "body": {}, "evaluators": []},
            )
            await client.post(
                "/v1/proxy",
                json={"target": "http://agent/v1", "body": {}, "evaluators": []},
            )

    with Session(storage.engine) as session:
        rows = session.exec(select(InvocationRecord)).all()
    assert len(rows) == 2
    # All unique invocation IDs
    assert len({r.invocation_id for r in rows}) == 2
