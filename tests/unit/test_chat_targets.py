"""Chat targets: openai-compatible + anthropic providers against fake servers."""
import pytest

from core.chat_targets import (
    CHAT_PROVIDERS,
    ChatProvider,
    ChatResult,
    ChatTarget,
    TargetError,
    build_provider,
    register_chat_provider,
    split_reasoning,
)
from core.dataset import Dataset
from tests.fake_chat_server import FakeChatServer


def _openai(srv, **kw):
    return build_provider(ChatTarget(
        provider="openai", base_url=f"{srv.url}/v1", model="m1", **kw))


@pytest.mark.asyncio
async def test_openai_request_shape_and_result():
    with FakeChatServer(lambda p: {"content": "hi"}) as srv:
        t = ChatTarget(provider="openai", base_url=f"{srv.url}/v1/", model="m1",
                       max_tokens=64, temperature=0.0, top_p=0.9, system="sys")
        res = await build_provider(t).complete("question")
    req = srv.requests[0]
    assert req["path"] == "/v1/chat/completions"
    assert req["body"] == {
        "model": "m1", "max_tokens": 64, "temperature": 0.0, "top_p": 0.9,
        "messages": [{"role": "system", "content": "sys"},
                     {"role": "user", "content": "question"}],
    }
    assert "Authorization" not in req["headers"]
    assert res.text == "hi" and res.provider == "openai" and res.model == "m1"
    assert res.usage == {"prompt_tokens": 7, "completion_tokens": 5, "total_tokens": 12}
    assert res.latency_ms is not None and res.latency_ms >= 0
    assert res.finish_reason == "stop"


@pytest.mark.asyncio
async def test_openai_omits_unset_params():
    with FakeChatServer(lambda p: {"content": "x"}) as srv:
        await _openai(srv).complete("q")
    assert set(srv.requests[0]["body"]) == {"model", "messages"}


@pytest.mark.asyncio
async def test_openai_bearer_from_api_key_env(monkeypatch):
    monkeypatch.setenv("MY_KEY_ENV", "sekret")
    with FakeChatServer(lambda p: {"content": "x"}) as srv:
        await _openai(srv, api_key_env="MY_KEY_ENV").complete("q")
    assert srv.requests[0]["headers"]["Authorization"] == "Bearer sekret"


@pytest.mark.asyncio
async def test_openai_never_guesses_openai_api_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "leak-me-not")
    with FakeChatServer(lambda p: {"content": "x"}) as srv:
        await _openai(srv).complete("q")
    assert "Authorization" not in srv.requests[0]["headers"]


@pytest.mark.asyncio
async def test_missing_api_key_env_is_target_error(monkeypatch):
    monkeypatch.delenv("NOPE_KEY", raising=False)
    with FakeChatServer(lambda p: {"content": "x"}) as srv, \
            pytest.raises(TargetError, match="NOPE_KEY"):
        await _openai(srv, api_key_env="NOPE_KEY").complete("q")
    assert srv.requests == []


@pytest.mark.asyncio
async def test_openai_reasoning_content_separated():
    with FakeChatServer(lambda p: {"content": "42", "reasoning_content": "thinking…"}) as srv:
        res = await _openai(srv).complete("q")
    assert res.text == "42" and res.reasoning == "thinking…"


@pytest.mark.asyncio
async def test_openai_reasoning_field_variant():
    with FakeChatServer(lambda p: {"content": "42", "reasoning": "hmm"}) as srv:
        res = await _openai(srv).complete("q")
    assert res.text == "42" and res.reasoning == "hmm"


@pytest.mark.asyncio
async def test_openai_inline_think_block_stripped():
    with FakeChatServer(lambda p: {"content": "<think>step 1\nstep 2</think>\n\nFinal answer: 6"}) as srv:
        res = await _openai(srv).complete("q")
    assert res.text == "Final answer: 6"
    assert res.reasoning == "step 1\nstep 2"


def test_split_reasoning_unopened_think():
    # chat templates that pre-fill "<think>" leave only the closing tag
    assert split_reasoning("plan it out</think>the answer") == ("the answer", "plan it out")


def test_split_reasoning_no_think():
    assert split_reasoning("plain") == ("plain", None)


@pytest.mark.asyncio
async def test_http_error_raises_target_error():
    with FakeChatServer(lambda p: {"status": 500, "error": "overloaded"}) as srv, \
            pytest.raises(TargetError, match="HTTP 500.*overloaded"):
        await _openai(srv).complete("q")


@pytest.mark.asyncio
async def test_connection_error_raises_target_error():
    t = ChatTarget(provider="openai", base_url="http://127.0.0.1:1/v1", model="m", timeout_s=2)
    with pytest.raises(TargetError):
        await build_provider(t).complete("q")


@pytest.mark.asyncio
async def test_malformed_body_raises_target_error():
    with FakeChatServer(lambda p: {"content": ""}) as srv:
        prov = _openai(srv)
        prov.parse_response = lambda body: body["choices"][5]  # IndexError
        with pytest.raises(TargetError, match="malformed"):
            await prov.complete("q")


@pytest.mark.asyncio
async def test_anthropic_request_shape_and_result(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ak")
    with FakeChatServer(lambda p: {"content": "ok", "thinking": "mull"}) as srv:
        t = ChatTarget(provider="anthropic", base_url=srv.url, model="claude-x",
                       max_tokens=100, temperature=0.2, system="be brief")
        res = await build_provider(t).complete("hello")
    req = srv.requests[0]
    assert req["path"] == "/v1/messages"
    assert req["headers"]["x-api-key"] == "ak"
    assert req["headers"]["anthropic-version"] == "2023-06-01"
    assert req["body"] == {
        "model": "claude-x", "max_tokens": 100, "temperature": 0.2, "system": "be brief",
        "messages": [{"role": "user", "content": "hello"}],
    }
    assert res.text == "ok" and res.reasoning == "mull"
    assert res.provider == "anthropic" and res.model == "claude-x"
    assert res.usage == {"prompt_tokens": 9, "completion_tokens": 4, "total_tokens": 13}


@pytest.mark.asyncio
@pytest.mark.parametrize("suffix", ["", "/v1", "/v1/messages"])
async def test_anthropic_base_url_forms(monkeypatch, suffix):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ak")
    with FakeChatServer(lambda p: {"content": "ok"}) as srv:
        t = ChatTarget(provider="anthropic", base_url=srv.url + suffix, model="c")
        await build_provider(t).complete("q")
    assert srv.requests[0]["path"] == "/v1/messages"
    assert srv.requests[0]["body"]["max_tokens"] == 4096  # required by the API


@pytest.mark.asyncio
async def test_anthropic_custom_api_key_env(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ALT_KEY", "alt")
    with FakeChatServer(lambda p: {"content": "ok"}) as srv:
        t = ChatTarget(provider="anthropic", base_url=srv.url, model="c", api_key_env="ALT_KEY")
        await build_provider(t).complete("q")
    assert srv.requests[0]["headers"]["x-api-key"] == "alt"


def test_label_and_defaults():
    t = ChatTarget(provider="openai", model="m", base_url="http://h:1/v1/")
    assert t.label == "openai:m@http://h:1/v1"
    assert ChatTarget(provider="anthropic", model="c").label == \
        "anthropic:c@https://api.anthropic.com"


def test_unknown_provider_rejected_by_dataset():
    with pytest.raises(ValueError, match="unknown chat provider"):
        Dataset(name="d", target={"provider": "nope", "model": "m"})


def test_unknown_target_field_rejected():
    with pytest.raises(ValueError):
        Dataset(name="d", target={"provider": "openai", "model": "m", "bogus": 1})


def test_dataset_mapping_target_sets_chat_and_label():
    ds = Dataset(name="d", target={"provider": "openai", "model": "m",
                                   "base_url": "http://h/v1"})
    assert ds.chat is not None and ds.chat.model == "m"
    assert ds.target == "openai:m@http://h/v1"


def test_dataset_url_target_unchanged():
    ds = Dataset(name="d", target="http://x/agent")
    assert ds.chat is None and ds.target == "http://x/agent"


@pytest.mark.asyncio
async def test_pluggable_provider():
    @register_chat_provider
    class Echo(ChatProvider):
        name = "echo"

        async def complete(self, prompt, client=None):
            return ChatResult(text=prompt.upper(), provider="echo", model=self.target.model)

    try:
        assert "echo" in CHAT_PROVIDERS
        ds = Dataset(name="d", target={"provider": "echo", "model": "e"})
        res = await build_provider(ds.chat).complete("abc")
        assert res.text == "ABC"
    finally:
        CHAT_PROVIDERS.pop("echo")
