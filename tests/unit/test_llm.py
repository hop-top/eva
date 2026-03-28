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
