# tests/server/test_auth.py
"""Tests for ApiKeyMiddleware — T-0053."""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch

from server.app import create_app
from server.auth import ApiKeyMiddleware


@pytest.fixture
def authed_app():
    """App instance with ApiKeyMiddleware wired via middleware_factories."""
    return create_app(middleware_factories=[ApiKeyMiddleware])


@pytest.fixture
def valid_key():
    return "eva_test_key_abc123"


@pytest.mark.asyncio
async def test_request_without_key_returns_401(authed_app):
    async with AsyncClient(
        transport=ASGITransport(app=authed_app), base_url="http://test"
    ) as client:
        resp = await client.post("/v1/proxy", json={"input": "hello"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Missing X-Eva-Key header"


@pytest.mark.asyncio
async def test_request_with_invalid_key_returns_401(authed_app):
    with patch("server.auth.state_adapter") as mock_state:
        mock_state.get = AsyncMock(return_value=None)
        async with AsyncClient(
            transport=ASGITransport(app=authed_app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/v1/proxy",
                json={"input": "hello"},
                headers={"X-Eva-Key": "bad_key"},
            )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid API key"


@pytest.mark.asyncio
async def test_request_with_valid_key_passes_auth(authed_app, valid_key):
    with patch("server.auth.state_adapter") as mock_state:
        mock_state.get = AsyncMock(return_value="1")
        async with AsyncClient(
            transport=ASGITransport(app=authed_app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/v1/proxy",
                json={"input": "hello", "target": "http://example.com"},
                headers={"X-Eva-Key": valid_key},
            )
    # Must NOT be 401 — downstream may fail, but auth passed
    assert resp.status_code != 401


@pytest.mark.asyncio
async def test_health_endpoint_exempt_from_auth(authed_app):
    async with AsyncClient(
        transport=ASGITransport(app=authed_app), base_url="http://test"
    ) as client:
        resp = await client.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_well_known_agent_json_exempt_from_auth(authed_app):
    async with AsyncClient(
        transport=ASGITransport(app=authed_app), base_url="http://test"
    ) as client:
        resp = await client.get("/.well-known/agent.json")
    # 200 or 404 — either fine; must NOT be 401
    assert resp.status_code != 401
