# tests/server/test_routes_proxy.py
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from server.app import app


def _make_proxy_response(text: str, status: int = 200):
    from server.gateway.proxy import ProxyResponse
    return ProxyResponse(status_code=status, text=text, headers={})


@pytest.mark.asyncio
async def test_proxy_passes_through_valid_response():
    with patch("server.gateway.routes.forward_request", new_callable=AsyncMock) as mock_fwd:
        mock_fwd.return_value = _make_proxy_response('{"answer": "hello"}')

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/proxy",
                json={
                    "target": "http://agent:8000/chat",
                    "body": {"input": "hi"},
                    "evaluators": [],
                },
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["eva_status"] == "pass"
    assert data["response"] == {"answer": "hello"}


@pytest.mark.asyncio
async def test_proxy_returns_contract_violation_on_eval_failure():
    with patch("server.gateway.routes.forward_request", new_callable=AsyncMock) as mock_fwd:
        mock_fwd.return_value = _make_proxy_response('{"answer": "bad"}')

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/proxy",
                json={
                    "target": "http://agent:8000/chat",
                    "body": {"input": "hi"},
                    "evaluators": [
                        {"name": "contains", "mode": "binary", "config": {"substring": "REQUIRED"}}
                    ],
                },
            )

    assert resp.status_code == 422
    data = resp.json()
    assert data["eva_status"] == "contract_violation"
    assert isinstance(data["violations"], list)
    assert data["attempts"] >= 1


@pytest.mark.asyncio
async def test_proxy_missing_target_returns_422():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/proxy",
            json={"body": {"input": "hi"}},  # missing target
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_proxy_upstream_error_returns_502():
    from server.gateway.proxy import ProxyError

    with patch("server.gateway.routes.forward_request", new_callable=AsyncMock) as mock_fwd:
        mock_fwd.side_effect = ProxyError("connection refused")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/proxy",
                json={"target": "http://dead:9999/", "body": {}, "evaluators": []},
            )

    assert resp.status_code == 502
    assert "connection refused" in resp.json()["detail"]
