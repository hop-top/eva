"""Runner + chat targets: scoring, run-store metadata, error handling."""
import json

import pytest

from core.chat_targets import ChatResult, build_provider
from core.dataset import Dataset
from core.plugins import make_manager
from core.query import compare_runs, get_invocation_detail, list_invocations
from core.runner import Runner
from core.storage import SqliteStorage
from tests.fake_chat_server import FakeChatServer

ADD_OK = "```python\ndef add(a, b):\n    return a + b\n```"
ADD_BAD = "```python\ndef add(a, b):\n    return a - b\n```"


def dataset(base_url, model="m1"):
    return Dataset(
        name="mini",
        target={"provider": "openai", "base_url": f"{base_url}/v1", "model": model},
        evaluators=[
            {"name": "code_tests", "mode": "binary", "timeout": 10},
            {"name": "final_answer", "mode": "binary"},
        ],
        tests=[
            {"id": "code-1", "input": "write add", "tests": "assert add(1, 2) == 3"},
            {"id": "reason-1", "input": "3+5-2?", "expected_output": "6"},
        ],
    )


def reply(prompt):
    if "add" in prompt:
        return {"content": ADD_OK, "reasoning_content": "use plus"}
    return {"content": "<think>3+5=8, 8-2=6</think>Final answer: 6"}


def runner(ds, storage):
    prov = build_provider(ds.chat)

    async def call(input, target):
        return await prov.complete(input)

    return Runner(pm=make_manager(), call_agent=call, storage=storage)


@pytest.mark.asyncio
async def test_scores_and_run_store_metadata():
    storage = SqliteStorage("sqlite:///:memory:")
    with FakeChatServer(reply) as srv:
        ds = dataset(srv.url)
        run = await runner(ds, storage).execute(ds)
    by = {(r.test_id, r.evaluator): r for r in run.results}
    assert by[("code-1", "code_tests")].passed
    assert by[("reason-1", "final_answer")].passed
    # evaluators skip cases that lack their fields (tests / expected_output)
    assert ("code-1", "final_answer") not in by
    assert ("reason-1", "code_tests") not in by
    assert run.skipped == []
    assert run.target == f"openai:m1@{srv.url}/v1"

    invs = {i.test_id: i for i in list_invocations(storage, run_id=run.run_id)}
    inv = invs["code-1"]
    assert inv.provider == "openai" and inv.model == "m1"
    detail = get_invocation_detail(storage, inv.invocation_id)
    (usage,) = detail["usage_records"]
    assert usage.scope == "agent" and usage.model == "m1"
    assert (usage.prompt_tokens, usage.completion_tokens, usage.total_tokens) == (7, 5, 12)
    assert usage.latency_ms is not None
    # reasoning stored separately; response artifact is the answer only
    kinds = {a.kind: a for a in detail["artifacts"]}
    assert kinds["reasoning"].text_content == "use plus"
    assert kinds["response"].text_content == ADD_OK
    # inline <think> block also separated
    d2 = get_invocation_detail(storage, invs["reason-1"].invocation_id)
    k2 = {a.kind: a for a in d2["artifacts"]}
    assert k2["reasoning"].text_content == "3+5=8, 8-2=6"
    assert k2["response"].text_content == "Final answer: 6"


@pytest.mark.asyncio
async def test_failure_reason_recorded_per_case():
    storage = SqliteStorage("sqlite:///:memory:")
    with FakeChatServer(lambda p: {"content": ADD_BAD}) as srv:
        ds = dataset(srv.url)
        run = await runner(ds, storage).execute(ds)
    r = next(r for r in run.results if r.test_id == "code-1" and r.evaluator == "code_tests")
    assert not r.passed and "AssertionError" in r.score.reason


@pytest.mark.asyncio
async def test_target_error_is_upstream_error_not_crash():
    storage = SqliteStorage("sqlite:///:memory:")
    with FakeChatServer(lambda p: {"status": 500, "error": "down"}) as srv:
        ds = dataset(srv.url)
        run = await runner(ds, storage).execute(ds)
    assert not run.passed
    assert {r.evaluator for r in run.results} == {"target"}
    assert len(run.results) == 2
    assert all("HTTP 500" in r.score.reason for r in run.results)
    invs = list_invocations(storage, run_id=run.run_id)
    assert {i.status for i in invs} == {"upstream_error"}
    detail = get_invocation_detail(storage, invs[0].invocation_id)
    assert "HTTP 500" in json.loads(detail["invocation"].metadata_json)["error"]


@pytest.mark.asyncio
async def test_url_style_str_return_still_works():
    ds = Dataset(name="d", target="http://x", evaluators=[{"name": "contains", "substring": "hi"}],
                 tests=[{"id": "t", "input": "i"}])

    async def call(i, t):
        return "hi there"

    run = await Runner(pm=make_manager(), call_agent=call).execute(ds)
    assert run.passed


@pytest.mark.asyncio
async def test_compare_shows_model_latency_tokens():
    storage = SqliteStorage("sqlite:///:memory:")
    runs = []
    for model in ("m-a", "m-b"):
        with FakeChatServer(reply) as srv:
            ds = dataset(srv.url, model=model)
            r = await runner(ds, storage).execute(ds)
            storage.save_run(r)
            runs.append(r)
    out = compare_runs(storage, runs[0].run_id, runs[1].run_id)
    assert set(out["left_stats"]["models"]) == {"m-a"}
    assert set(out["right_stats"]["models"]) == {"m-b"}
    assert out["left_stats"]["prompt_tokens"] == 14
    assert out["left_stats"]["avg_latency_ms"] is not None
    assert out["evaluator_diffs"]["code_tests"]["left_pass_rate"] == 1.0


@pytest.mark.asyncio
async def test_chat_result_text_only_return():
    ds = Dataset(name="d", target="http://x", evaluators=[{"name": "exact_match"}],
                 tests=[{"id": "t", "input": "i", "expected_output": "6"}])

    async def call(i, t):
        return ChatResult(text="6", reasoning="because")

    run = await Runner(pm=make_manager(), call_agent=call).execute(ds)
    assert run.passed


@pytest.mark.asyncio
async def test_case_with_no_applicable_evaluator_is_noted():
    ds = Dataset(name="d", target="http://x", evaluators=[{"name": "exact_match"}],
                 tests=[{"id": "orphan", "input": "i"}])

    async def call(i, t):
        return "x"

    run = await Runner(pm=make_manager(), call_agent=call).execute(ds)
    assert run.results == [] and any("orphan" in s for s in run.skipped)
