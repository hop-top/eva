# tests/server/test_gateway_sampling.py
"""Gateway sampling: artifact writes follow sample_rate; invocation stubs always persist."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, ASGITransport
from sqlmodel import Session, select

from core.storage import ArtifactRecord, InvocationRecord, SqliteStorage
from server.app import create_app
from server.gateway import routes as gateway_routes


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def storage(tmp_path):
    return SqliteStorage(db_url=f"sqlite:///{tmp_path}/test_sampling.db")


@pytest.fixture
def app_with_storage(storage):
    _app = create_app()
    gateway_routes.set_storage(storage)
    yield _app
    gateway_routes.set_storage(None)
    gateway_routes.set_sample_rate(1.0)  # reset to default after each test


def _proxy_response(text: str, status: int = 200):
    from server.gateway.proxy import ProxyResponse
    return ProxyResponse(status_code=status, text=text, headers={})


async def _post_proxy(client: AsyncClient, body: dict | None = None) -> None:
    await client.post(
        "/v1/proxy",
        json={
            "target": "http://agent/chat",
            "body": body or {"q": "hello"},
            "evaluators": [],
        },
    )


# ---------------------------------------------------------------------------
# sample_rate = 1.0: all requests persist artifacts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sample_rate_1_each_invocation_has_artifact_refs(app_with_storage, storage):
    """sample_rate=1.0 - every InvocationRecord has non-None artifact IDs."""
    gateway_routes.set_sample_rate(1.0)

    with patch("server.gateway.routes.forward_request", new_callable=AsyncMock) as mock_fwd:
        mock_fwd.return_value = _proxy_response('{"ok": true}')
        async with AsyncClient(
            transport=ASGITransport(app=app_with_storage), base_url="http://test"
        ) as client:
            await _post_proxy(client)

    with Session(storage.engine) as session:
        rows = session.exec(select(InvocationRecord)).all()

    assert len(rows) == 1
    assert rows[0].request_artifact_id is not None
    assert rows[0].response_artifact_id is not None


# ---------------------------------------------------------------------------
# sample_rate = 0.0: no artifacts written, Invocation stub still recorded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sample_rate_0_no_artifacts_written(app_with_storage, storage):
    """sample_rate=0.0 - ArtifactRecord rows are never written."""
    gateway_routes.set_sample_rate(0.0)

    with patch("server.gateway.routes.forward_request", new_callable=AsyncMock) as mock_fwd:
        mock_fwd.return_value = _proxy_response('{"answer": "ok"}')
        async with AsyncClient(
            transport=ASGITransport(app=app_with_storage), base_url="http://test"
        ) as client:
            for _ in range(5):
                await _post_proxy(client)

    with Session(storage.engine) as session:
        art_rows = session.exec(select(ArtifactRecord)).all()

    assert art_rows == [], "No artifact rows should exist at sample_rate=0.0"


@pytest.mark.asyncio
async def test_sample_rate_0_invocation_stub_recorded(app_with_storage, storage):
    """sample_rate=0.0 - InvocationRecord stub is still written (counts stay accurate)."""
    gateway_routes.set_sample_rate(0.0)

    with patch("server.gateway.routes.forward_request", new_callable=AsyncMock) as mock_fwd:
        mock_fwd.return_value = _proxy_response('{"ok": true}')
        async with AsyncClient(
            transport=ASGITransport(app=app_with_storage), base_url="http://test"
        ) as client:
            await _post_proxy(client)
            await _post_proxy(client)

    with Session(storage.engine) as session:
        inv_rows = session.exec(select(InvocationRecord)).all()

    assert len(inv_rows) == 2
    for row in inv_rows:
        assert row.request_artifact_id is None
        assert row.response_artifact_id is None


# ---------------------------------------------------------------------------
# sample_rate = 0.5: a request is sampled when random() < rate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sample_rate_half_follows_random_draw(app_with_storage, storage):
    """Draws 0.1 and 0.49 are sampled; 0.5 and 0.9 are not (stubs remain)."""
    gateway_routes.set_sample_rate(0.5)

    with patch("server.gateway.routes.forward_request", new_callable=AsyncMock) as mock_fwd, \
            patch("server.gateway.routes.random.random", side_effect=[0.1, 0.49, 0.5, 0.9]):
        mock_fwd.return_value = _proxy_response('{"r": "x"}')
        async with AsyncClient(
            transport=ASGITransport(app=app_with_storage), base_url="http://test"
        ) as client:
            for _ in range(4):
                await _post_proxy(client)

    with Session(storage.engine) as session:
        inv_rows = session.exec(select(InvocationRecord)).all()

    assert len(inv_rows) == 4
    assert sum(r.request_artifact_id is not None for r in inv_rows) == 2
    assert sum(r.request_artifact_id is None for r in inv_rows) == 2
