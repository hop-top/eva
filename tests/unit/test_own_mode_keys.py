"""``mode`` is only the pass mode; refusal and sentence_paragraph_count keep
their own setting under ``refusal_mode`` / ``count_mode``.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from core.contract import ContractValidationError, load_contract
from core.dataset import Dataset
from core.evaluators.builtin import BUILTIN_EVALUATOR_FACTORIES
from core.evaluators.errors import EvaluatorConfigError, build_evaluator
from core.plugins import make_manager
from core.runner import Runner

REFUSAL = "I'm sorry, but I can't help with that request."
TEXT = "First sentence. Second sentence.\n\nSecond paragraph."

# (evaluator, own key, own value, response that passes with it, response that fails)
CASES = [
    ("refusal", "refusal_mode", "require", REFUSAL, "Sure, here is the answer."),
    ("refusal", "refusal_mode", "forbid", "Sure, here is the answer.", REFUSAL),
    ("sentence_paragraph_count", "count_mode", "paragraph", TEXT, None),
]
OLD = [
    ("refusal", "forbid", "refusal_mode"),
    ("refusal", "require", "refusal_mode"),
    ("sentence_paragraph_count", "sentence", "count_mode"),
    ("sentence_paragraph_count", "paragraph", "count_mode"),
]


def _msg(name, value, key):
    return f"evaluator {name!r}: mode {value!r} is not a pass mode; set {key}: {value}"


def _run_dataset(entry, text):
    async def call(prompt, target):
        return text

    ds = Dataset(name="d", target="http://x", evaluators=[entry],
                 tests=[{"id": "t", "input": "hi"}])
    return Runner(pm=make_manager(), call_agent=call).execute(ds)


# ---- new keys work, on all three paths ------------------------------------

@pytest.mark.asyncio
async def test_dataset_refusal_mode_with_each_pass_mode():
    for pass_mode in ("binary", "threshold", "warn"):
        entry = {"name": "refusal", "refusal_mode": "require", "mode": pass_mode}
        ok = await _run_dataset(entry, REFUSAL)
        assert ok.results[0].mode == pass_mode and ok.results[0].score.value == 1.0
        bad = await _run_dataset(entry, "Sure, here you go.")
        assert bad.results[0].score.value == 0.0


@pytest.mark.asyncio
async def test_dataset_count_mode_paragraph():
    entry = {"name": "sentence_paragraph_count", "count_mode": "paragraph",
             "max": 2, "mode": "binary"}
    run = await _run_dataset(entry, TEXT)
    assert run.results[0].score.value == 1.0 and run.results[0].mode == "binary"
    run = await _run_dataset({**entry, "max": 1}, TEXT)
    assert run.results[0].score.value == 0.0


@pytest.mark.asyncio
async def test_dataset_defaults_unchanged():
    run = await _run_dataset({"name": "refusal"}, "Sure, here you go.")
    assert run.results[0].score.value == 1.0


@pytest.mark.parametrize("name,key,value,good,bad", CASES)
def test_contract_new_keys(tmp_path, name, key, value, good, bad):
    f = tmp_path / "c.yaml"
    f.write_text(yaml.dump({"name": "c", "provider": "x", "evaluators": [
        {"name": name, key: value, "mode": "threshold", "min_score": 0.5, "max": 2}]}))
    c = load_contract(f)
    assert c.evaluators[0].mode == "threshold"
    ev = build_evaluator(name, BUILTIN_EVALUATOR_FACTORIES[name],
                         c.evaluators[0].__pydantic_extra__, None)
    assert ev.run(good).value == 1.0
    if bad:
        assert ev.run(bad).value == 0.0


@pytest.mark.asyncio
async def test_gateway_new_key_in_config():
    from server.app import create_app
    from server.gateway.proxy import ProxyResponse

    app = create_app()
    with patch("server.gateway.routes.forward_request", new_callable=AsyncMock) as fwd:
        fwd.return_value = ProxyResponse(status_code=200, text=REFUSAL, headers={})
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.post("/v1/proxy", json={
                "target": "http://a.invalid/x", "body": {},
                "evaluators": [{"name": "refusal", "mode": "threshold", "min_score": 0.5,
                                "config": {"refusal_mode": "require"}}]})
    assert r.status_code == 200, r.text


# ---- old own-value `mode` errors naming the new key ------------------------

@pytest.mark.parametrize("name,value,key", OLD)
@pytest.mark.asyncio
async def test_dataset_old_mode_errors(name, value, key):
    calls = []

    async def call(prompt, target):
        calls.append(prompt)
        return "x"

    ds = Dataset(name="d", target="http://x", evaluators=[{"name": name, "mode": value}],
                 tests=[{"id": "t", "input": "hi"}])
    with pytest.raises(EvaluatorConfigError) as exc:
        await Runner(pm=make_manager(), call_agent=call).execute(ds)
    assert str(exc.value) == _msg(name, value, key) and calls == []


@pytest.mark.parametrize("name,value,key", OLD)
def test_contract_old_mode_errors(tmp_path, name, value, key):
    f = tmp_path / "c.yaml"
    f.write_text(yaml.dump({"name": "c", "provider": "x",
                            "evaluators": [{"name": name, "mode": value}]}))
    with pytest.raises(ContractValidationError) as exc:
        load_contract(f)
    assert str(exc.value) == _msg(name, value, key)


@pytest.mark.parametrize("name,value,key", OLD)
@pytest.mark.asyncio
async def test_gateway_old_config_mode_errors(name, value, key):
    from server.app import create_app

    app = create_app()
    with patch("server.gateway.routes.forward_request", new_callable=AsyncMock) as fwd:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.post("/v1/proxy", json={
                "target": "http://a.invalid/x", "body": {},
                "evaluators": [{"name": name, "config": {"mode": value}}]})
        fwd.assert_not_called()
    assert r.status_code == 422 and r.json()["detail"] == _msg(name, value, key)


@pytest.mark.parametrize("name,value,key", OLD)
@pytest.mark.asyncio
async def test_gateway_old_spec_mode_errors(name, value, key):
    from server.app import create_app

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/v1/proxy", json={
            "target": "http://a.invalid/x", "body": {},
            "evaluators": [{"name": name, "mode": value}]})
    assert r.status_code == 422 and _msg(name, value, key) in r.text


def test_other_non_pass_mode_is_a_config_error():
    with pytest.raises(EvaluatorConfigError, match="mode 'sideways' is not a pass mode"):
        build_evaluator("refusal", BUILTIN_EVALUATOR_FACTORIES["refusal"],
                        {"mode": "sideways"}, None)


@pytest.mark.parametrize("name,key,bad", [("refusal", "refusal_mode", "sideways"),
                                          ("sentence_paragraph_count", "count_mode", "word")])
def test_bad_own_value_names_the_key(name, key, bad):
    with pytest.raises(EvaluatorConfigError) as exc:
        build_evaluator(name, BUILTIN_EVALUATOR_FACTORIES[name], {key: bad}, None)
    assert key in str(exc.value) and bad in str(exc.value)
