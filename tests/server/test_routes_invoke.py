# tests/server/test_routes_invoke.py
import pytest
import yaml
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch


@pytest.fixture
def app_with_registry(tmp_path):
    """Return a fresh app instance with a contract loaded into its registry."""
    from server.app import create_app
    from server.contracts.registry import ContractRegistry

    contract_data = {
        "name": "echo_policy",
        "provider": "http://echo-agent:8000/respond",
        "request_schema": {
            "type": "object",
            "required": ["message"],
            "properties": {"message": {"type": "string"}},
        },
        "evaluators": [{"name": "contains", "mode": "binary"}],
        "retry_policy": {"max_retries": 1, "hint": "Include a greeting"},
    }
    f = tmp_path / "echo_policy.yaml"
    f.write_text(yaml.dump(contract_data))

    registry = ContractRegistry()
    registry.load_file(f)
    return create_app(registry=registry)


@pytest.mark.asyncio
async def test_invoke_validates_request_schema(app_with_registry):
    async with AsyncClient(
        transport=ASGITransport(app=app_with_registry), base_url="http://test"
    ) as client:
        # Missing required 'message' field
        resp = await client.post(
            "/v1/contract/invoke",
            json={"contract": "echo_policy", "body": {}},
        )
    assert resp.status_code == 400
    data = resp.json()
    assert data["eva_status"] == "request_invalid"
    assert len(data["violations"]) > 0


@pytest.mark.asyncio
async def test_invoke_passes_valid_request(app_with_registry):
    from server.gateway.proxy import ProxyResponse

    with patch("server.gateway.routes.forward_request", new_callable=AsyncMock) as mock_fwd:
        mock_fwd.return_value = ProxyResponse(
            status_code=200, text='{"reply": "hello"}', headers={}
        )
        async with AsyncClient(
            transport=ASGITransport(app=app_with_registry), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/v1/contract/invoke",
                json={"contract": "echo_policy", "body": {"message": "hi"}},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["eva_status"] == "pass"


@pytest.mark.asyncio
async def test_invoke_unknown_contract_returns_404(app_with_registry):
    async with AsyncClient(
        transport=ASGITransport(app=app_with_registry), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/v1/contract/invoke",
            json={"contract": "nonexistent", "body": {"message": "hi"}},
        )
    assert resp.status_code == 404
