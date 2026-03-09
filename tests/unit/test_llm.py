# tests/unit/test_llm.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from core.llm import LiteLLMAdapter


@pytest.mark.asyncio
async def test_complete_returns_content():
    fake_response = MagicMock()
    fake_response.choices[0].message.content = "Hello, world!"

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:
        mock_acompletion.return_value = fake_response
        adapter = LiteLLMAdapter(model="gpt-4o-mini")
        result = await adapter.complete([{"role": "user", "content": "Hi"}])

    assert result == "Hello, world!"
    mock_acompletion.assert_awaited_once()
    call_kwargs = mock_acompletion.call_args
    assert call_kwargs.kwargs["model"] == "gpt-4o-mini"
    assert call_kwargs.kwargs["messages"] == [{"role": "user", "content": "Hi"}]


@pytest.mark.asyncio
async def test_complete_passes_extra_kwargs():
    fake_response = MagicMock()
    fake_response.choices[0].message.content = "result"

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
    fake_response = MagicMock()
    fake_response.choices[0].message.content = "x"

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:
        mock_acompletion.return_value = fake_response
        adapter = LiteLLMAdapter(temperature=0.2)
        await adapter.complete([{"role": "user", "content": "q"}], temperature=0.9)

    assert mock_acompletion.call_args.kwargs["temperature"] == 0.9
