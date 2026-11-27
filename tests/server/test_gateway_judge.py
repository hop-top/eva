"""Judge evaluators in the gateway, on /v1/contract/invoke and /v1/proxy.

`litellm.acompletion` is always mocked; no request leaves the process.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from core.llm import LiteLLMAdapter
from server.contracts.registry import ContractRegistry
from server.gateway.proxy import ProxyResponse

ROUTES = ["invoke", "proxy"]
RELEVANCE = {"name": "relevance", "mode": "threshold", "min_score": 0.5}


def _resp(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=None,
        model="m",
    )


@pytest.fixture(autouse=True)
def _reset_judge(monkeypatch):
    for k in ("EVA_JUDGE_MODEL", "EVA_JUDGE_BASE_URL"):
        monkeypatch.delenv(k, raising=False)
    yield
    from server.gateway import routes

    reset = getattr(routes, "set_judge_adapter", None)
    if reset is not None:
        reset(None)


def _adapter():
    return LiteLLMAdapter("openai/judge-model")


def _make_app(tmp_path, evaluators, prompt_field, max_retries, adapter):
    from server.app import create_app

    data = {
        "name": "judged",
        "provider": "http://agent.invalid/respond",
        "evaluators": evaluators,
        "retry_policy": {"max_retries": max_retries},
    }
    if prompt_field is not None:
        data["prompt_field"] = prompt_field
    f = tmp_path / "judged.yaml"
    f.write_text(yaml.dump(data))
    registry = ContractRegistry()
    registry.load_file(f)
    kwargs = {} if adapter is None else {"judge_adapter": adapter}
    return create_app(registry=registry, **kwargs)


async def call(
    tmp_path,
    route,
    evaluators,
    body,
    *,
    prompt_field="question",
    max_retries=0,
    adapter=None,
    agent_texts=("RESPONSE-R",),
):
    """POST through `route`; the agent answers with `agent_texts` in order."""
    app = _make_app(tmp_path, evaluators, prompt_field, max_retries, adapter)
    with patch("server.gateway.routes.forward_request", new_callable=AsyncMock) as fwd:
        fwd.side_effect = [
            ProxyResponse(status_code=200, text=t, headers={}) for t in agent_texts
        ] + [ProxyResponse(status_code=200, text=agent_texts[-1], headers={})] * 5
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            if route == "invoke":
                resp = await client.post(
                    "/v1/contract/invoke", json={"contract": "judged", "body": body}
                )
            else:
                specs = [
                    {
                        "name": e["name"],
                        "mode": e.get("mode", "binary"),
                        "min_score": e.get("min_score", 1.0),
                        "config": {
                            k: v
                            for k, v in e.items()
                            if k not in ("name", "mode", "min_score")
                        },
                    }
                    for e in evaluators
                ]
                payload = {
                    "target": "http://agent.invalid/respond",
                    "body": body,
                    "evaluators": specs,
                    "max_retries": max_retries,
                }
                if prompt_field is not None:
                    payload["prompt_field"] = prompt_field
                resp = await client.post("/v1/proxy", json=payload)
    return resp


def _sent(mock) -> str:
    return json.dumps([c.kwargs["messages"] for c in mock.await_args_list])


# --- the 500 this feature removes -------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
async def test_judge_evaluator_without_judge_is_not_a_500(tmp_path, route):
    resp = await call(
        tmp_path,
        route,
        [RELEVANCE, {"name": "contains", "substring": "RESP"}],
        {"question": "q"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["eva_status"] == "pass"
    assert body["skipped"] == [
        {"evaluator": "relevance", "reason": "no judge model configured"}
    ]


# --- judge runs --------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
async def test_prompt_and_response_reach_judge_call(tmp_path, route):
    with patch("litellm.acompletion", new_callable=AsyncMock) as m:
        m.return_value = _resp("0.9\nfits")
        resp = await call(
            tmp_path,
            route,
            [RELEVANCE, {"name": "contains", "substring": "RESP"}],
            {"question": "PROMPT-Q-3", "other": "x"},
            adapter=_adapter(),
            agent_texts=("RESPONSE-R-7",),
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["eva_status"] == "pass" and "skipped" not in body
    m.assert_awaited_once()
    sent = _sent(m)
    assert "PROMPT-Q-3" in sent and "RESPONSE-R-7" in sent
    assert m.await_args.kwargs["model"] == "openai/judge-model"


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
async def test_judge_verdict_below_threshold_is_422_violation(tmp_path, route):
    with patch("litellm.acompletion", new_callable=AsyncMock) as m:
        m.return_value = _resp("0.2\noff topic")
        resp = await call(
            tmp_path,
            route,
            [RELEVANCE, {"name": "tool_use"}],
            {"question": "q"},
            adapter=_adapter(),
        )
    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body["eva_status"] == "contract_violation"
    (v,) = body["violations"]
    assert v["evaluator"] == "relevance" and v["score"] == 0.2
    assert "off topic" in v["reason"]
    assert [s["evaluator"] for s in body["skipped"]] == ["tool_use"]


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
async def test_failing_judge_call_is_a_violation_not_a_500(tmp_path, route):
    with patch("litellm.acompletion", new_callable=AsyncMock) as m:
        m.side_effect = RuntimeError("endpoint down\nsecond line")
        resp = await call(
            tmp_path, route, [RELEVANCE], {"question": "q"}, adapter=_adapter()
        )
    assert resp.status_code == 422, resp.text
    (v,) = resp.json()["violations"]
    assert v["evaluator"] == "relevance" and v["score"] == 0.0
    assert v["reason"] == "judge error: RuntimeError: endpoint down"


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
async def test_each_retry_attempt_judges_that_attempts_response(tmp_path, route):
    with patch("litellm.acompletion", new_callable=AsyncMock) as m:
        m.return_value = _resp("0.0\nbad")
        resp = await call(
            tmp_path,
            route,
            [RELEVANCE],
            {"question": "PROMPT-Q"},
            max_retries=2,
            adapter=_adapter(),
            agent_texts=("ATTEMPT-ONE", "ATTEMPT-TWO", "ATTEMPT-THREE"),
        )
    assert resp.status_code == 422
    assert resp.json()["attempts"] == 3
    assert m.await_count == 3
    for call_, text in zip(
        m.await_args_list, ("ATTEMPT-ONE", "ATTEMPT-TWO", "ATTEMPT-THREE")
    ):
        sent = json.dumps(call_.kwargs["messages"])
        assert text in sent and "PROMPT-Q" in sent


@pytest.mark.asyncio
async def test_judge_built_from_configuration_when_not_injected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EVA_JUDGE_MODEL", "openai/from-env")
    monkeypatch.setenv("EVA_JUDGE_BASE_URL", "http://judge.invalid/v1")
    with patch("litellm.acompletion", new_callable=AsyncMock) as m:
        m.return_value = _resp("1.0\nok")
        resp = await call(tmp_path, "invoke", [RELEVANCE], {"question": "q"})
    assert resp.status_code == 200, resp.text
    assert m.await_args.kwargs["model"] == "openai/from-env"
    assert m.await_args.kwargs["api_base"] == "http://judge.invalid/v1"


# --- skips -------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize(
    "name, needs",
    [
        ("tool_correctness", "tool events"),
        ("plan_adherence", "planned steps"),
        ("ragas", "retrieval context"),
    ],
)
async def test_skip_when_evaluator_needs_inputs_gateway_cannot_supply(
    tmp_path, route, name, needs
):
    with patch("litellm.acompletion", new_callable=AsyncMock) as m:
        resp = await call(
            tmp_path,
            route,
            [{"name": name}, {"name": "contains", "substring": "RESP"}],
            {"question": "q"},
            adapter=_adapter(),
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["skipped"] == [
        {
            "evaluator": name,
            "reason": f"needs {needs}, which the gateway cannot supply "
            "(use dataset mode)",
        }
    ]
    m.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
async def test_skip_when_no_model_even_if_inputs_missing(tmp_path, route):
    # reason order: no judge model comes before the needs-inputs reason
    resp = await call(tmp_path, route, [{"name": "tool_use"}], {"question": "q"})
    assert resp.status_code == 200
    assert resp.json()["skipped"][0]["reason"] == "no judge model configured"


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
async def test_skip_when_contract_has_no_prompt_field(tmp_path, route):
    with patch("litellm.acompletion", new_callable=AsyncMock) as m:
        resp = await call(
            tmp_path,
            route,
            [RELEVANCE],
            {"question": "q"},
            prompt_field=None,
            adapter=_adapter(),
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["skipped"] == [
        {
            "evaluator": "relevance",
            "reason": "judge evaluators need the request prompt: set prompt_field",
        }
    ]
    m.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
async def test_skip_when_body_lacks_prompt_field(tmp_path, route):
    with patch("litellm.acompletion", new_callable=AsyncMock) as m:
        resp = await call(
            tmp_path, route, [RELEVANCE], {"other": "x"}, adapter=_adapter()
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["skipped"] == [
        {"evaluator": "relevance", "reason": "request body has no field 'question'"}
    ]
    m.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("value", [7, None, ["a"], {"k": "v"}])
async def test_skip_when_prompt_field_is_not_a_string(tmp_path, route, value):
    with patch("litellm.acompletion", new_callable=AsyncMock) as m:
        resp = await call(
            tmp_path, route, [RELEVANCE], {"question": value}, adapter=_adapter()
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["skipped"] == [
        {
            "evaluator": "relevance",
            "reason": "request body field 'question' is not a string",
        }
    ]
    m.assert_not_awaited()


@pytest.mark.asyncio
async def test_prompt_field_is_top_level_only(tmp_path):
    with patch("litellm.acompletion", new_callable=AsyncMock) as m:
        resp = await call(
            tmp_path,
            "invoke",
            [RELEVANCE],
            {"a": {"question": "nested"}},
            prompt_field="a.question",
            adapter=_adapter(),
        )
    assert resp.json()["skipped"][0]["reason"] == (
        "request body has no field 'a.question'"
    )
    m.assert_not_awaited()


# --- contracts without judge evaluators are unchanged -------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
async def test_contract_without_judge_evaluators_response_unchanged(tmp_path, route):
    with patch("litellm.acompletion", new_callable=AsyncMock) as m:
        ok = await call(
            tmp_path,
            route,
            [{"name": "contains", "substring": "RESP"}],
            {"question": "q"},
            adapter=_adapter(),
        )
        bad = await call(
            tmp_path,
            route,
            [{"name": "contains", "substring": "NOPE"}],
            {"question": "q"},
            adapter=_adapter(),
        )
    m.assert_not_awaited()
    assert ok.status_code == 200 and bad.status_code == 422
    assert set(ok.json()) == {"eva_status", "attempts", "response", "request_id", "trace_id"}
    assert set(bad.json()) == {
        "eva_status", "attempts", "violations", "request_id", "trace_id",
    }
