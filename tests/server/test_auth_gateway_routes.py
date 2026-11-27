# tests/server/test_auth_gateway_routes.py
"""API-key auth is applied to every gateway route when auth is enabled.

Auth is enabled by configuring a key store (EVA_REDIS_URL). `create_app()`
must install the key check itself; callers must not have to remember to pass
the middleware through `middleware_factories`.
"""
import pytest
import yaml
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch

from server.app import create_app
from server.auth import ApiKeyMiddleware
from server.contracts.registry import ContractRegistry
from server.gateway.proxy import ProxyResponse

VALID_KEY = "eva_test_key"

INVOKE_BODY = {"contract": "echo_policy", "body": {"message": "hi"}}
PROXY_BODY = {
    "target": "http://agent.invalid/respond",
    "body": {"message": "hi"},
    "evaluators": [{"name": "contains", "config": {"substring": "hello"}}],
}

# One entry per gateway route that acts on a caller's behalf.
PROTECTED_ROUTES = [
    ("/v1/contract/invoke", INVOKE_BODY),
    ("/v1/proxy", PROXY_BODY),
]


@pytest.fixture
def auth_enabled(monkeypatch):
    monkeypatch.setenv("EVA_REDIS_URL", "redis://key-store.invalid:6379/0")


@pytest.fixture
def key_store():
    async def fake_get(key: str):
        return "1" if key == f"eva:apikey:{VALID_KEY}" else None

    with patch("server.auth.state_adapter") as mock:
        mock.get = AsyncMock(side_effect=fake_get)
        yield mock


@pytest.fixture
def gateway(auth_enabled, key_store, tmp_path):
    f = tmp_path / "echo_policy.yaml"
    f.write_text(yaml.dump({
        "name": "echo_policy",
        "provider": "http://agent.invalid/respond",
        "request_schema": {
            "type": "object",
            "required": ["message"],
            "properties": {"message": {"type": "string"}},
        },
        "evaluators": [{"name": "contains", "mode": "binary", "substring": "hello"}],
    }))
    registry = ContractRegistry()
    registry.load_file(f)
    return create_app(registry=registry)


async def _post(app, path, body, headers=None):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        return await c.post(path, json=body, headers=headers or {})


@pytest.mark.asyncio
@pytest.mark.parametrize("path,body", PROTECTED_ROUTES)
async def test_no_key_is_401_with_structured_error(gateway, path, body):
    resp = await _post(gateway, path, body)
    assert resp.status_code == 401
    data = resp.json()
    assert data["detail"] == "Missing X-Eva-Key header"
    assert data["eva_status"] == "unauthorized"
    assert data["violations"] == [
        {"field": "X-Eva-Key", "message": "Missing X-Eva-Key header"}
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("path,body", PROTECTED_ROUTES)
async def test_wrong_key_is_401_with_structured_error(gateway, path, body):
    resp = await _post(gateway, path, body, {"X-Eva-Key": "wrong_key"})
    assert resp.status_code == 401
    data = resp.json()
    assert data["detail"] == "Invalid API key"
    assert data["eva_status"] == "unauthorized"
    assert data["violations"] == [{"field": "X-Eva-Key", "message": "Invalid API key"}]


@pytest.mark.asyncio
@pytest.mark.parametrize("path,body", PROTECTED_ROUTES)
async def test_valid_key_is_handled_as_before(gateway, path, body):
    with patch("server.gateway.routes.forward_request", new_callable=AsyncMock) as fwd:
        fwd.return_value = ProxyResponse(
            status_code=200, text='{"reply": "hello"}', headers={}
        )
        resp = await _post(gateway, path, body, {"X-Eva-Key": VALID_KEY})
    assert resp.status_code == 200
    assert resp.json()["eva_status"] == "pass"


@pytest.mark.asyncio
async def test_no_key_does_not_reach_the_agent(gateway):
    with patch("server.gateway.routes.forward_request", new_callable=AsyncMock) as fwd:
        resp = await _post(gateway, "/v1/contract/invoke", INVOKE_BODY)
    assert resp.status_code == 401
    fwd.assert_not_called()


@pytest.mark.asyncio
async def test_every_v1_route_requires_a_key(gateway):
    """Any route mounted under /v1 is covered, including future ones."""
    paths = {p for p in gateway.openapi()["paths"] if p.startswith("/v1/")}
    assert {p for p, _ in PROTECTED_ROUTES} <= paths
    async with AsyncClient(transport=ASGITransport(app=gateway), base_url="http://test") as c:
        for path in sorted(paths):
            for method in ("GET", "POST"):
                resp = await c.request(method, path)
                assert resp.status_code == 401, (method, path)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/health", "/openapi.json", "/docs", "/redoc"])
async def test_exempt_paths_stay_open(gateway, path):
    async with AsyncClient(transport=ASGITransport(app=gateway), base_url="http://test") as c:
        resp = await c.get(path)
    assert resp.status_code == 200


def test_explicit_middleware_is_not_installed_twice(auth_enabled, key_store):
    app = create_app(middleware_factories=[ApiKeyMiddleware])
    installed = [m for m in app.user_middleware if m.cls is ApiKeyMiddleware]
    assert len(installed) == 1
