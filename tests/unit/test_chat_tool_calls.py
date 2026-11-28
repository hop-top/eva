"""Chat target tool definitions: sent per case; returned calls recorded."""
import json

import pytest

from core.chat_targets import build_provider
from core.dataset import Dataset, EvaTestCase
from core.events import ToolCallEvent
from core.plugins import EvaPlugin, EvaSpec, make_manager
from core.query import get_invocation_detail
from core.runner import Runner
from core.storage import SqliteStorage
from tests.fake_chat_server import FakeChatServer

WEATHER = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Current weather",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
}
TIME = {
    "type": "function",
    "function": {"name": "get_time", "parameters": {"type": "object", "properties": {}}},
}


class Capture(EvaPlugin):
    def __init__(self):
        self.ctx = None

    @EvaSpec.hook_impl
    def run_eval(self, response, context):
        from core.models import Score
        self.ctx = context
        return Score(value=1.0)


def dataset(base_url, provider="openai", **case):
    target = {"provider": provider, "model": "m1", "api_key_env": None}
    target["base_url"] = f"{base_url}/v1" if provider == "openai" else base_url
    return Dataset(
        name="tc",
        target=target,
        evaluators=[{"name": "x", "mode": "binary"}],
        tests=[{"id": "c1", "input": "weather in Paris?", **case}],
    )


async def run(ds, storage=None):
    prov = build_provider(ds.chat)

    async def call(input, target, tools=None, tool_choice=None):
        return await prov.complete(input, tools=tools, tool_choice=tool_choice)

    cap = Capture()
    pm = make_manager()
    pm.register(cap)
    r = await Runner(pm=pm, call_agent=call, storage=storage).execute(ds)
    return r, cap.ctx


@pytest.mark.asyncio
async def test_request_carries_tools_and_tool_choice():
    with FakeChatServer(lambda p: {"content": "hi"}) as srv:
        await run(dataset(srv.url, tools=[WEATHER], tool_choice="required"))
    body = srv.requests[0]["body"]
    assert body["tools"] == [WEATHER]
    assert body["tool_choice"] == "required"


@pytest.mark.asyncio
async def test_request_without_tools_has_no_tool_keys():
    with FakeChatServer(lambda p: {"content": "hi"}) as srv:
        await run(dataset(srv.url))
    body = srv.requests[0]["body"]
    assert "tools" not in body and "tool_choice" not in body


@pytest.mark.asyncio
async def test_no_call_records_empty_log():
    with FakeChatServer(lambda p: {"content": "sunny"}) as srv:
        r, ctx = await run(dataset(srv.url, tools=[WEATHER]))
    assert r.passed
    assert ctx["tool_events"] == []
    assert len(srv.requests) == 1


@pytest.mark.asyncio
async def test_one_call_recorded():
    reply = {"content": "", "tool_calls": [
        {"name": "get_weather", "arguments": '{"city": "Paris"}'}]}
    with FakeChatServer(lambda p: reply) as srv:
        _, ctx = await run(dataset(srv.url, tools=[WEATHER]))
    (ev,) = ctx["tool_events"]
    assert isinstance(ev, ToolCallEvent)
    assert (ev.tool_name, ev.args, ev.step_index, ev.raw_args) == (
        "get_weather", {"city": "Paris"}, 0, None)
    assert len(srv.requests) == 1  # no follow-up turn


@pytest.mark.asyncio
async def test_parallel_calls_keep_order():
    reply = {"content": "", "tool_calls": [
        {"name": "get_weather", "arguments": {"city": "Paris"}},
        {"name": "get_time", "arguments": "{}"},
        {"name": "get_weather", "arguments": {"city": "Rome"}},
    ]}
    with FakeChatServer(lambda p: reply) as srv:
        _, ctx = await run(dataset(srv.url, tools=[WEATHER, TIME]))
    evs = ctx["tool_events"]
    assert [(e.step_index, e.tool_name, e.args) for e in evs] == [
        (0, "get_weather", {"city": "Paris"}),
        (1, "get_time", {}),
        (2, "get_weather", {"city": "Rome"}),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ['{"city": "Par', "", "[1, 2]", "not json"])
async def test_malformed_arguments_keep_raw_string(bad):
    reply = {"content": "", "tool_calls": [
        {"name": "get_weather", "arguments": bad},
        {"name": "get_time", "arguments": "{}"},
    ]}
    with FakeChatServer(lambda p: reply) as srv:
        r, ctx = await run(dataset(srv.url, tools=[WEATHER]))
    first, second = ctx["tool_events"]
    assert first.args == {} and first.raw_args == bad
    assert second.args == {} and second.raw_args is None  # valid "{}"
    assert r.results[0].passed


@pytest.mark.asyncio
async def test_calls_persisted_with_raw_args_in_invocation_view():
    reply = {"content": "", "tool_calls": [
        {"name": "get_weather", "arguments": '{"city": "Paris"}'},
        {"name": "get_weather", "arguments": '{"city": '},
    ]}
    storage = SqliteStorage("sqlite:///:memory:")
    with FakeChatServer(lambda p: reply) as srv:
        await run(dataset(srv.url, tools=[WEATHER]), storage)
    from core.query import list_invocations
    inv = list_invocations(storage)[0]
    detail = get_invocation_detail(storage, inv.invocation_id)
    calls = detail["tool_calls"]
    assert [(c.step_index, c.tool_name, c.raw_args) for c in calls] == [
        (0, "get_weather", None), (1, "get_weather", '{"city": ')]
    arts = {a.artifact_id: a for a in detail["artifacts"]}
    assert json.loads(arts[calls[0].args_artifact_id].json_content) == {"city": "Paris"}


@pytest.mark.asyncio
async def test_anthropic_translates_and_parses():
    reply = {"content": "", "tool_calls": [
        {"name": "get_weather", "arguments": {"city": "Paris"}}]}
    with FakeChatServer(lambda p: reply) as srv:
        import os
        os.environ["EVA_TEST_ANTHROPIC_KEY"] = "k"
        ds = dataset(srv.url, provider="anthropic", tools=[WEATHER],
                     tool_choice={"type": "function", "function": {"name": "get_weather"}})
        ds.chat.api_key_env = "EVA_TEST_ANTHROPIC_KEY"
        _, ctx = await run(ds)
    body = srv.requests[0]["body"]
    assert body["tools"] == [{
        "name": "get_weather", "description": "Current weather",
        "input_schema": WEATHER["function"]["parameters"]}]
    assert body["tool_choice"] == {"type": "tool", "name": "get_weather"}
    (ev,) = ctx["tool_events"]
    assert (ev.tool_name, ev.args, ev.raw_args) == ("get_weather", {"city": "Paris"}, None)


def test_tool_choice_requires_tools():
    with pytest.raises(ValueError, match="tool_choice requires tools"):
        EvaTestCase(id="a", input="x", tool_choice="auto")


def test_dataset_yaml_case_carries_tools(tmp_path):
    from core.dataset import load_dataset
    p = tmp_path / "d.yaml"
    p.write_text(
        "name: d\ntarget: {provider: openai, model: m, base_url: 'http://x/v1'}\n"
        "tests:\n  - id: a\n    input: hi\n    tool_choice: auto\n    tools:\n"
        "      - type: function\n        function: {name: f, parameters: {type: object}}\n"
    )
    t = load_dataset(p).tests[0]
    assert t.tools[0]["function"]["name"] == "f" and t.tool_choice == "auto"
