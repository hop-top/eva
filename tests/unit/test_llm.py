# tests/unit/test_llm.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from core.llm import LiteLLMAdapter, build_vision_message


def _make_fake_response(content: str) -> MagicMock:
    """Build a MagicMock that satisfies LLMCompletion field extraction."""
    fake = MagicMock()
    fake.choices[0].message.content = content
    fake.model = "gpt-4o-mini"
    fake._hidden_params = {"custom_llm_provider": "openai"}
    fake.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    fake.model_dump = MagicMock(return_value={"id": "test"})
    return fake


@pytest.mark.asyncio
async def test_complete_returns_content():
    fake_response = _make_fake_response("Hello, world!")

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:
        mock_acompletion.return_value = fake_response
        adapter = LiteLLMAdapter(model="gpt-4o-mini")
        result = await adapter.complete([{"role": "user", "content": "Hi"}])

    assert result.content == "Hello, world!"
    mock_acompletion.assert_awaited_once()
    call_kwargs = mock_acompletion.call_args
    assert call_kwargs.kwargs["model"] == "gpt-4o-mini"
    assert call_kwargs.kwargs["messages"] == [{"role": "user", "content": "Hi"}]


@pytest.mark.asyncio
async def test_complete_passes_extra_kwargs():
    fake_response = _make_fake_response("result")

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:
        mock_acompletion.return_value = fake_response
        adapter = LiteLLMAdapter(model="gpt-3.5-turbo", temperature=0.5)
        await adapter.complete([{"role": "user", "content": "q"}], max_tokens=100)

    call_kwargs = mock_acompletion.call_args.kwargs
    assert call_kwargs["temperature"] == 0.5
    assert call_kwargs["max_tokens"] == 100


@pytest.mark.asyncio
async def test_complete_call_kwargs_override_constructor():
    """Per-call kwargs override constructor kwargs."""
    fake_response = _make_fake_response("x")

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:
        mock_acompletion.return_value = fake_response
        adapter = LiteLLMAdapter(temperature=0.2)
        await adapter.complete([{"role": "user", "content": "q"}], temperature=0.9)

    assert mock_acompletion.call_args.kwargs["temperature"] == 0.9


# ---------------------------------------------------------------------------
# build_vision_message
# ---------------------------------------------------------------------------

def test_build_vision_message_structure():
    msg = build_vision_message("Describe this", "https://example.com/img.png")
    assert msg["role"] == "user"
    assert isinstance(msg["content"], list)
    assert len(msg["content"]) == 2
    assert msg["content"][0] == {"type": "text", "text": "Describe this"}
    assert msg["content"][1] == {
        "type": "image_url",
        "image_url": {"url": "https://example.com/img.png"},
    }


@pytest.mark.asyncio
async def test_complete_accepts_vision_message():
    """LiteLLMAdapter.complete() passes image_url content messages to litellm."""
    fake_response = _make_fake_response("It is a cat.")

    vision_msg = build_vision_message("What is this?", "https://example.com/cat.jpg")
    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:
        mock_acompletion.return_value = fake_response
        adapter = LiteLLMAdapter(model="gpt-4o")
        result = await adapter.complete([vision_msg])

    assert result.content == "It is a cat."
    sent_messages = mock_acompletion.call_args.kwargs["messages"]
    assert sent_messages[0]["role"] == "user"
    assert isinstance(sent_messages[0]["content"], list)


# ---------------------------------------------------------------------------
# Robust usage extraction (regression for brittle dict(usage_obj))
# ---------------------------------------------------------------------------

from core.llm import _extract_usage


class _AttrUsage:
    """Plain attribute-style usage object — like OpenAI SDK's CompletionUsage."""

    def __init__(self, prompt_tokens: int, completion_tokens: int, total_tokens: int):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens


def test_extract_usage_from_dict():
    """Plain dict / Mapping usage objects pass straight through."""
    usage_dict = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    out = _extract_usage(usage_dict)
    assert out == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


def test_extract_usage_from_attribute_object():
    """Attribute-style usage objects extract canonical token fields."""
    usage = _AttrUsage(prompt_tokens=20, completion_tokens=8, total_tokens=28)
    out = _extract_usage(usage)
    assert out["prompt_tokens"] == 20
    assert out["completion_tokens"] == 8
    assert out["total_tokens"] == 28


def test_extract_usage_from_none_returns_empty():
    """Missing / None usage yields empty dict — must NOT crash."""
    assert _extract_usage(None) == {}


def test_extract_usage_from_malformed_object_returns_empty():
    """An object with no relevant fields and no dump method yields {}."""

    class _Useless:
        pass

    assert _extract_usage(_Useless()) == {}


def test_extract_usage_prefers_model_dump_over_attrs():
    """Pydantic-style .model_dump() output wins when present."""

    class _PydanticLike:
        prompt_tokens = 1
        completion_tokens = 1
        total_tokens = 2

        def model_dump(self):
            return {"prompt_tokens": 99, "completion_tokens": 11, "total_tokens": 110}

    out = _extract_usage(_PydanticLike())
    assert out == {"prompt_tokens": 99, "completion_tokens": 11, "total_tokens": 110}
