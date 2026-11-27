"""POST /v1/contract/evaluate: score output the caller already holds.

No provider call, no retry, no request_schema check, nothing persisted.
`litellm.acompletion` is always mocked; no request leaves the process.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from core.llm import LiteLLMAdapter
from server.app import create_app
from server.contracts.registry import ContractRegistry
from tests.server.test_auth_gateway_routes import VALID_KEY, auth_enabled, key_store  # noqa: F401

DEAD_PROVIDER = "http://provider.invalid/respond"
RELEVANCE = {"name": "relevance", "mode": "threshold", "min_score": 0.5}

CONTRACTS = {
    "plain": {
        "name": "plain",
        "provider": DEAD_PROVIDER,
        "request_schema": {"type": "object", "required": ["never"]},
        "evaluators": [{"name": "contains", "substring": "hello"}],
        "retry_policy": {"max_retries": 2},
    },
    "execres": {
        "name": "execres",
        "provider": DEAD_PROVIDER,
        "evaluators": [{"name": "contains", "substring": "all good", "field": "stdout"}],
    },
    "exitcode": {
        "name": "exitcode",
        "provider": DEAD_PROVIDER,
        "evaluators": [
            {"name": "exit_code", "expected": 0},
            {"name": "regex", "pattern": "done [0-9]+", "field": "stdout"},
        ],
    },
    "judged": {
        "name": "judged",
        "provider": DEAD_PROVIDER,
        "prompt_field": "question",
        "evaluators": [RELEVANCE, {"name": "contains", "substring": "hello"}],
    },
    "skiponly": {
        "name": "skiponly",
        "provider": DEAD_PROVIDER,
        "evaluators": [{"name": "tool_use"}],
    },
}


def _resp(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=None,
        model="m",
    )


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    for k in ("EVA_JUDGE_MODEL", "EVA_JUDGE_BASE_URL"):
        monkeypatch.delenv(k, raising=False)
    yield
    from server.gateway import routes

    routes.set_judge_adapter(None)
    routes.set_storage(None)
    routes.set_registry(None)


def _registry(tmp_path) -> ContractRegistry:
    registry = ContractRegistry()
    for name, data in CONTRACTS.items():
        f = tmp_path / f"{name}.yaml"
        f.write_text(yaml.dump(data))
        registry.load_file(f)
    return registry


@pytest.fixture
def app(tmp_path):
    return create_app(registry=_registry(tmp_path))


@pytest.fixture
def judge_app(tmp_path):
    return create_app(
        registry=_registry(tmp_path), judge_adapter=LiteLLMAdapter("openai/judge-model")
    )


async def post(app, payload, headers=None):
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as c:
        return await c.post("/v1/contract/evaluate", json=payload, headers=headers or {})


# --- string output -----------------------------------------------------------


@pytest.mark.asyncio
async def test_string_output_pass(app):
    resp = await post(app, {"contract": "plain", "output": "well hello there"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["eva_status"] == "pass"


@pytest.mark.asyncio
async def test_string_output_violation(app):
    resp = await post(app, {"contract": "plain", "output": "nothing here"})
    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body["eva_status"] == "contract_violation"
    (v,) = body["violations"]
    assert v["evaluator"] == "contains" and v["score"] == 0.0 and "hello" in v["reason"]


@pytest.mark.asyncio
async def test_string_output_is_not_reserialised(app):
    resp = await post(app, {"contract": "execres", "output": "plain text, all good"})
    # a plain string is not JSON: the field-scoped evaluator cannot read it
    assert resp.status_code == 422, resp.text


# --- object output -----------------------------------------------------------


@pytest.mark.asyncio
async def test_object_output_is_scored_by_top_level_field(app):
    ok = {"exit_code": 0, "stdout": "all good\n", "stderr": ""}
    bad = {"exit_code": 0, "stdout": "boom", "stderr": "all good"}
    assert (await post(app, {"contract": "execres", "output": ok})).status_code == 200
    resp = await post(app, {"contract": "execres", "output": bad})
    assert resp.status_code == 422, resp.text
    assert resp.json()["violations"][0]["evaluator"] == "contains"


@pytest.mark.asyncio
async def test_exit_code_evaluator_reads_command_result(app):
    ok = {"exit_code": 0, "stdout": "done 42"}
    assert (await post(app, {"contract": "exitcode", "output": ok})).status_code == 200
    resp = await post(app, {"contract": "exitcode", "output": {**ok, "exit_code": 1}})
    assert resp.status_code == 422, resp.text
    assert [v["evaluator"] for v in resp.json()["violations"]] == ["exit_code"]


@pytest.mark.asyncio
async def test_object_output_is_scored_as_json_text(app):
    """Whole-text evaluators see the JSON text of the object."""
    ok = await post(app, {"contract": "plain", "output": {"greeting": "hello"}})
    assert ok.status_code == 200, ok.text
    bad = await post(app, {"contract": "plain", "output": {"greeting": "bye"}})
    assert bad.status_code == 422, bad.text


@pytest.mark.asyncio
@pytest.mark.parametrize("output", [[1, 2], 3, 1.5, True, None])
async def test_non_string_non_object_output_is_rejected(app, output):
    resp = await post(app, {"contract": "plain", "output": output})
    assert resp.status_code == 422
    assert "eva_status" not in resp.json()
    assert isinstance(resp.json()["detail"], list)


@pytest.mark.asyncio
async def test_missing_output_or_contract_is_rejected(app):
    for payload in ({"contract": "plain"}, {"output": "x"}):
        resp = await post(app, payload)
        assert resp.status_code == 422
        assert "eva_status" not in resp.json()


@pytest.mark.asyncio
async def test_empty_prompt_is_rejected(app):
    resp = await post(app, {"contract": "plain", "output": "hello", "prompt": ""})
    assert resp.status_code == 422
    assert "eva_status" not in resp.json()


@pytest.mark.asyncio
async def test_unknown_extra_keys_are_ignored(app):
    resp = await post(app, {"contract": "plain", "output": "hello", "body": {"x": 1}, "z": 2})
    assert resp.status_code == 200, resp.text


# --- 404 / 503 ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_contract_is_404(app):
    resp = await post(app, {"contract": "nope", "output": "x"})
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Contract 'nope' not found"}


@pytest.mark.asyncio
async def test_registry_not_initialised_is_503():
    from server.gateway import routes

    app = create_app()
    routes.set_registry(None)  # create_app() keeps a registry wired by an earlier app
    resp = await post(app, {"contract": "plain", "output": "x"})
    assert resp.status_code == 503
    assert resp.json() == {"detail": "Contract registry not initialized"}


# --- auth --------------------------------------------------------------------


@pytest.fixture
def authed(auth_enabled, key_store, tmp_path):  # noqa: F811
    return create_app(registry=_registry(tmp_path))


@pytest.mark.asyncio
async def test_no_key_is_401(authed):
    resp = await post(authed, {"contract": "plain", "output": "hello"})
    assert resp.status_code == 401
    assert resp.json()["eva_status"] == "unauthorized"


@pytest.mark.asyncio
async def test_valid_key_is_200(authed):
    resp = await post(
        authed, {"contract": "plain", "output": "hello"}, {"X-Eva-Key": VALID_KEY}
    )
    assert resp.status_code == 200, resp.text


# --- judge evaluators ----------------------------------------------------------


@pytest.mark.asyncio
async def test_judge_skipped_without_prompt_names_prompt_not_prompt_field(judge_app):
    with patch("litellm.acompletion", new_callable=AsyncMock) as m:
        resp = await post(judge_app, {"contract": "judged", "output": "hello"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["skipped"] == [
        {"evaluator": "relevance", "reason": "judge evaluators need the request prompt: send prompt"}
    ]
    m.assert_not_awaited()


@pytest.mark.asyncio
async def test_judge_runs_with_prompt(judge_app):
    with patch("litellm.acompletion", new_callable=AsyncMock) as m:
        m.return_value = _resp("0.9\nfits")
        resp = await post(
            judge_app,
            {"contract": "judged", "output": "hello RESPONSE-R", "prompt": "PROMPT-Q-3"},
        )
    assert resp.status_code == 200, resp.text
    assert "skipped" not in resp.json()
    m.assert_awaited_once()
    sent = json.dumps(m.await_args.kwargs["messages"])
    assert "PROMPT-Q-3" in sent and "RESPONSE-R" in sent


@pytest.mark.asyncio
async def test_judge_below_threshold_is_violation(judge_app):
    with patch("litellm.acompletion", new_callable=AsyncMock) as m:
        m.return_value = _resp("0.2\noff topic")
        resp = await post(
            judge_app, {"contract": "judged", "output": "hello", "prompt": "q"}
        )
    assert resp.status_code == 422, resp.text
    (v,) = resp.json()["violations"]
    assert v["evaluator"] == "relevance" and v["score"] == 0.2


@pytest.mark.asyncio
async def test_judge_failure_scores_zero_not_500(judge_app):
    with patch("litellm.acompletion", new_callable=AsyncMock) as m:
        m.side_effect = RuntimeError("endpoint down\nsecond line")
        resp = await post(
            judge_app, {"contract": "judged", "output": "hello", "prompt": "q"}
        )
    assert resp.status_code == 422, resp.text
    (v,) = resp.json()["violations"]
    assert v["score"] == 0.0
    assert v["reason"] == "judge error: RuntimeError: endpoint down"


@pytest.mark.asyncio
async def test_no_judge_configured_skips(app):
    resp = await post(app, {"contract": "judged", "output": "hello", "prompt": "q"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["skipped"] == [
        {"evaluator": "relevance", "reason": "no judge model configured"}
    ]


# --- exact key sets --------------------------------------------------------------


def _keys(resp) -> list[str]:
    return list(resp.json())


@pytest.mark.asyncio
async def test_200_key_sets(app):
    plain = await post(app, {"contract": "plain", "output": "hello"})
    assert _keys(plain) == ["eva_status", "request_id", "trace_id"]
    skipped = await post(app, {"contract": "judged", "output": "hello"})
    assert _keys(skipped) == ["eva_status", "skipped", "request_id", "trace_id"]


@pytest.mark.asyncio
async def test_422_key_sets(app):
    plain = await post(app, {"contract": "plain", "output": "bye"})
    assert plain.status_code == 422
    assert _keys(plain) == ["eva_status", "violations", "request_id", "trace_id"]
    skipped = await post(app, {"contract": "judged", "output": "bye"})
    assert skipped.status_code == 422
    assert _keys(skipped) == ["eva_status", "violations", "skipped", "request_id", "trace_id"]


@pytest.mark.asyncio
async def test_only_skipped_evaluators_pass(app):
    resp = await post(app, {"contract": "skiponly", "output": "x"})
    assert resp.status_code == 200
    assert resp.json()["skipped"][0]["evaluator"] == "tool_use"


# --- no provider, no retry, no schema, no persistence -----------------------------


@pytest.mark.asyncio
async def test_provider_is_never_called(app):
    with patch(
        "server.gateway.routes.forward_request",
        new_callable=AsyncMock,
        side_effect=AssertionError("provider called"),
    ) as fwd:
        ok = await post(app, {"contract": "plain", "output": "hello"})
        bad = await post(app, {"contract": "plain", "output": "bye"})
    assert ok.status_code == 200 and bad.status_code == 422
    fwd.assert_not_called()


@pytest.mark.asyncio
async def test_no_retry_and_no_request_schema_check(app):
    """`plain` has max_retries=2 and an unsatisfiable request_schema."""
    with patch("litellm.acompletion", new_callable=AsyncMock):
        resp = await post(app, {"contract": "plain", "output": "bye"})
    assert resp.status_code == 422  # not 400 request_invalid
    assert "attempts" not in resp.json() and "response" not in resp.json()


@pytest.mark.asyncio
async def test_nothing_is_persisted(app):
    from server.gateway import routes

    storage = MagicMock()
    routes.set_storage(storage)
    await post(app, {"contract": "plain", "output": "hello"})
    await post(app, {"contract": "plain", "output": "bye"})
    assert storage.method_calls == []
