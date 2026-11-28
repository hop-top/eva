"""Gateway: a bad non-judge evaluator config reports the real message.

A contract with one is skipped at load with a warning carrying it, so no
invoke/evaluate request can reach it; an inline /v1/proxy evaluator answers 422.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from server.app import create_app
from server.contracts.registry import ContractRegistry

GOOD = {"name": "good", "provider": "http://agent.invalid/x",
        "evaluators": [{"name": "contains", "substring": "hi"}]}
BAD = {"name": "bad", "provider": "http://agent.invalid/x",
       "evaluators": [{"name": "contains", "substring": "hi"},
                      {"name": "mood", "expected": "grumpy"}]}


def _dir(tmp_path):
    (tmp_path / "good.yaml").write_text(yaml.dump(GOOD))
    (tmp_path / "bad.yaml").write_text(yaml.dump(BAD))
    return tmp_path


def test_load_dir_skips_bad_contract_with_real_message(tmp_path):
    reg = ContractRegistry()
    with pytest.warns(UserWarning) as rec:
        reg.load_dir(_dir(tmp_path))
    msgs = [str(w.message) for w in rec]
    assert len(msgs) == 1
    assert "bad.yaml" in msgs[0] and "evaluator 'mood':" in msgs[0] and "grumpy" in msgs[0]
    assert "no judge model" not in msgs[0]
    assert reg.list_names() == ["good"]


def test_load_file_raises_real_message(tmp_path):
    f = _dir(tmp_path) / "bad.yaml"
    with pytest.raises(Exception, match="evaluator 'mood': .*grumpy"):
        ContractRegistry().load_file(f)


@pytest.mark.asyncio
async def test_invoke_and_evaluate_never_reach_bad_contract(tmp_path):
    reg = ContractRegistry()
    with pytest.warns(UserWarning):
        reg.load_dir(_dir(tmp_path))
    app = create_app(registry=reg)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r1 = await c.post("/v1/contract/invoke", json={"contract": "bad", "body": {}})
        r2 = await c.post("/v1/contract/evaluate", json={"contract": "bad", "output": "hi"})
        ok = await c.post("/v1/contract/evaluate", json={"contract": "good", "output": "hi"})
    assert (r1.status_code, r2.status_code, ok.status_code) == (404, 404, 200)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "spec, needle",
    [
        ({"name": "mood", "config": {"expected": "grumpy"}}, "grumpy"),
        ({"name": "refusal", "config": {"mode": "sideways"}}, "sideways"),
        ({"name": "regex", "config": {"pattern": "("}}, "'('"),
    ],
)
async def test_proxy_inline_bad_evaluator_is_422_with_real_message(spec, needle):
    app = create_app()
    with patch("server.gateway.routes.forward_request", new_callable=AsyncMock) as fwd:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.post("/v1/proxy", json={
                "target": "http://agent.invalid/x", "body": {"input": "hi"},
                "evaluators": [spec],
            })
        fwd.assert_not_called()
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert f"evaluator {spec['name']!r}: " in detail and needle in detail
    assert "no judge model" not in r.text


@pytest.mark.asyncio
async def test_proxy_judge_without_adapter_still_skips():
    app = create_app()
    from server.gateway.proxy import ProxyResponse
    with patch("server.gateway.routes.forward_request", new_callable=AsyncMock) as fwd:
        fwd.return_value = ProxyResponse(status_code=200, text="hi", headers={})
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.post("/v1/proxy", json={
                "target": "http://agent.invalid/x", "body": {"input": "hi"},
                "evaluators": [{"name": "relevance"}],
            })
    assert r.status_code == 200
    assert r.json()["skipped"] == [
        {"evaluator": "relevance", "reason": "no judge model configured"}
    ]


def test_queue_evaluator_map_raises_config_error():
    from core.evaluators.errors import EvaluatorConfigError
    from server.gateway.routes import EvaluatorSpec, _build_evaluator_map

    spec = EvaluatorSpec(name="mood", config={"expected": "grumpy"})
    with pytest.raises(EvaluatorConfigError, match="evaluator 'mood': .*grumpy"):
        _build_evaluator_map([spec])
