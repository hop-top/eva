"""key_facts' derived pass rule through the gateway routes."""
from __future__ import annotations

import warnings
from unittest.mock import AsyncMock, patch

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from core.contract import ContractValidationError
from server.app import create_app
from server.contracts.registry import ContractRegistry
from server.gateway.proxy import ProxyResponse

FACTS = ["Paris", "1889", "330 m", "Gustave Eiffel"]
THREE_OF_FOUR = "Paris, 1889, 330 m."


def _contract(name, **evaluator):
    return {
        "name": name,
        "provider": "http://provider.invalid/respond",
        "evaluators": [{"name": "key_facts", "required": FACTS, **evaluator}],
    }


CONTRACTS = {
    "loose": _contract("loose", threshold=0.75),
    "strict": _contract("strict"),
    "binary": _contract("binary", mode="binary"),
    "plain": {
        "name": "plain",
        "provider": "http://provider.invalid/respond",
        "evaluators": [{"name": "contains", "substring": "Paris"}],
    },
}


@pytest.fixture(autouse=True)
def _reset():
    yield
    from server.gateway import routes

    routes.set_judge_adapter(None)
    routes.set_storage(None)
    routes.set_registry(None)


@pytest.fixture
def app(tmp_path):
    registry = ContractRegistry()
    for name, data in CONTRACTS.items():
        f = tmp_path / f"{name}.yaml"
        f.write_text(yaml.dump(data))
        registry.load_file(f)
    return create_app(registry=registry)


async def post(app, path, payload):
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as c:
        return await c.post(path, json=payload)


@pytest.mark.asyncio
async def test_evaluate_threshold_passes_three_of_four(app):
    r = await post(app, "/v1/contract/evaluate", {"contract": "loose", "output": THREE_OF_FOUR})
    assert r.status_code == 200, r.text
    assert r.json()["eva_status"] == "pass"


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["strict", "binary"])
async def test_evaluate_default_and_explicit_binary_need_all(app, name):
    r = await post(app, "/v1/contract/evaluate", {"contract": name, "output": THREE_OF_FOUR})
    assert r.status_code == 422
    (v,) = r.json()["violations"]
    assert v["score"] == 0.75


@pytest.mark.asyncio
async def test_evaluate_other_evaluator_unchanged(app):
    ok = await post(app, "/v1/contract/evaluate", {"contract": "plain", "output": "Paris"})
    bad = await post(app, "/v1/contract/evaluate", {"contract": "plain", "output": "Rome"})
    assert ok.status_code == 200 and bad.status_code == 422


@pytest.mark.asyncio
async def test_invoke_threshold_passes_three_of_four(app):
    with patch("server.gateway.routes.forward_request", new_callable=AsyncMock) as fwd:
        fwd.return_value = ProxyResponse(status_code=200, text=THREE_OF_FOUR, headers={})
        loose = await post(app, "/v1/contract/invoke", {"contract": "loose", "body": {}})
        strict = await post(app, "/v1/contract/invoke", {"contract": "strict", "body": {}})
    assert loose.status_code == 200 and loose.json()["eva_status"] == "pass"
    assert strict.status_code != 200


def _proxy(evaluator):
    return {"target": "http://agent/x", "body": {}, "evaluators": [evaluator]}


@pytest.mark.asyncio
async def test_proxy_threshold_passes_three_of_four():
    from server.app import app as default_app

    cfg = {"required": FACTS, "threshold": 0.75}
    with patch("server.gateway.routes.forward_request", new_callable=AsyncMock) as fwd:
        fwd.return_value = ProxyResponse(status_code=200, text=THREE_OF_FOUR, headers={})
        ok = await post(default_app, "/v1/proxy", _proxy({"name": "key_facts", "config": cfg}))
        strict = await post(
            default_app, "/v1/proxy", _proxy({"name": "key_facts", "config": {"required": FACTS}})
        )
        binary = await post(
            default_app,
            "/v1/proxy",
            _proxy({"name": "key_facts", "mode": "binary", "config": {"required": FACTS}}),
        )
    assert ok.status_code == 200 and ok.json()["eva_status"] == "pass"
    assert strict.status_code != 200 and binary.status_code != 200


@pytest.mark.asyncio
async def test_proxy_conflict_is_422_with_message():
    from server.app import app as default_app

    bad = {"name": "key_facts", "mode": "binary", "config": {"required": FACTS, "threshold": 0.5}}
    r = await post(default_app, "/v1/proxy", _proxy(bad))
    assert r.status_code == 422
    assert "conflicts with mode: binary" in r.text


def test_registry_conflict_load_file_raises(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text(yaml.dump(_contract("bad", mode="binary", threshold=0.5)))
    with pytest.raises(ContractValidationError, match="conflicts"):
        ContractRegistry().load_file(f)


def test_registry_conflict_load_dir_skips_with_warning(tmp_path):
    (tmp_path / "bad.yaml").write_text(yaml.dump(_contract("bad", min_score=0.2, threshold=0.5)))
    (tmp_path / "ok.yaml").write_text(yaml.dump(CONTRACTS["loose"]))
    reg = ContractRegistry()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        reg.load_dir(tmp_path)
    assert reg.list_names() == ["loose"]
    assert any("conflicts" in str(x.message) for x in w)
