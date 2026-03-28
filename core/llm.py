# core/llm.py
from typing import Any

from pydantic import BaseModel


class LLMCompletion(BaseModel):
    """Structured result from LiteLLMAdapter.complete()."""

    content: str
    provider: str | None
    model: str
    usage: dict
    raw_response: dict | None


class LiteLLMAdapter:
    """Async LLM adapter backed by LiteLLM.

    Requires the optional 'llm' extra: uv add --optional llm litellm
    """

    def __init__(self, model: str = "gpt-4o-mini", **kwargs: Any):
        self.model = model
        self.kwargs = kwargs

    async def complete(
        self, messages: list[dict[str, str]], **kwargs: Any
    ) -> LLMCompletion:
        import litellm  # deferred — only required when adapter is used

        response = await litellm.acompletion(
            model=self.model,
            messages=messages,
            **{**self.kwargs, **kwargs},
        )
        content = response.choices[0].message.content

        usage_obj = getattr(response, "usage", None)
        usage: dict = dict(usage_obj) if usage_obj is not None else {}

        raw_response: dict | None = None
        try:
            raw_response = response.model_dump()
        except Exception:
            pass

        return LLMCompletion(
            content=content,
            provider=getattr(response, "_hidden_params", {}).get("custom_llm_provider"),
            model=getattr(response, "model", self.model),
            usage=usage,
            raw_response=raw_response,
        )


def build_vision_message(text: str, image_url: str) -> dict:
    """Build an OpenAI-style vision message with text and image_url content parts."""
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": image_url}},
        ],
    }
