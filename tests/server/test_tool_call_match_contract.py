"""tool_call_match has no case and no tool-call log in the gateway."""
import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from server.app import create_app
from server.contracts.registry import ContractRegistry


@pytest.mark.asyncio
async def test_evaluate_route_scores_zero_with_reason(tmp_path):
    f = tmp_path / "calls.yaml"
    f.write_text(yaml.dump({
        "name": "calls",
        "provider": "http://provider.invalid/respond",
        "evaluators": [{"name": "tool_call_match", "match": "none"}],
    }))
    registry = ContractRegistry()
    registry.load_file(f)
    app = create_app(registry=registry)
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as c:
        resp = await c.post(
            "/v1/contract/evaluate", json={"contract": "calls", "output": "hi"}
        )
    assert resp.status_code == 422, resp.text
    (v,) = resp.json()["violations"]
    assert v["evaluator"] == "tool_call_match" and v["score"] == 0.0
    assert "tool-call log" in v["reason"]
