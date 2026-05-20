# core/llm.py
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel


class LLMCompletion(BaseModel):
    """Structured result from LiteLLMAdapter.complete()."""

    content: str
    provider: str | None
    model: str
    usage: dict
    raw_response: dict | None


def _extract_usage(usage_obj: Any) -> dict:
    """Coerce a LiteLLM usage object into a plain dict.

    Handles three shapes a provider may return:

      1. Mapping / dict — used directly.
      2. Pydantic model or dataclass-style object — pulled via .model_dump()
         (or vars()/__dict__ as a fallback).
      3. Plain attribute object — manual extraction of prompt_tokens,
         completion_tokens, total_tokens.

    Returns {} for None or anything that yields nothing usable. Never raises
    on malformed inputs — callers depend on this to keep token capture from
    crashing the whole call.
    """
    if usage_obj is None:
        return {}

    # 1. Mapping protocol — covers dict and dict-like objects.
    if isinstance(usage_obj, Mapping):
        try:
            return dict(usage_obj)
        except Exception:
            pass

    # 2. Pydantic-style .model_dump() (preferred — emits canonical keys).
    model_dump = getattr(usage_obj, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump()
            if isinstance(dumped, Mapping):
                return dict(dumped)
        except Exception:
            pass

    # 3. __dict__ fallback — covers vanilla dataclass / SimpleNamespace.
    obj_dict = getattr(usage_obj, "__dict__", None)
    if isinstance(obj_dict, dict) and obj_dict:
        return {k: v for k, v in obj_dict.items() if not k.startswith("_")}

    # 4. Plain attribute access — last resort.
    fields = ("prompt_tokens", "completion_tokens", "total_tokens")
    extracted = {f: getattr(usage_obj, f, None) for f in fields}
    if any(v is not None for v in extracted.values()):
        return {k: v for k, v in extracted.items() if v is not None}

    return {}


class LiteLLMAdapter:
    """Async LLM adapter backed by LiteLLM.

    Requires the optional 'llm' extra: uv add --optional llm litellm
    """

    def __init__(self, model: str = "gpt-4o-mini", **kwargs: Any):
        self.model = model
        self.kwargs = kwargs

    async def complete(
        self, messages: list[dict[str, Any]], **kwargs: Any
    ) -> LLMCompletion:
        import litellm  # deferred — only required when adapter is used

        response = await litellm.acompletion(
            model=self.model,
            messages=messages,
            **{**self.kwargs, **kwargs},
        )
        content = response.choices[0].message.content

        usage_obj = getattr(response, "usage", None)
        usage: dict = _extract_usage(usage_obj)

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
