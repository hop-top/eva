# core/llm.py
from typing import Any


class LiteLLMAdapter:
    """Async LLM adapter backed by LiteLLM.

    Requires the optional 'llm' extra: uv add --optional llm litellm
    """

    def __init__(self, model: str = "gpt-4o-mini", **kwargs: Any):
        self.model = model
        self.kwargs = kwargs

    async def complete(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        import litellm  # deferred — only required when adapter is used

        response = await litellm.acompletion(
            model=self.model,
            messages=messages,
            **{**self.kwargs, **kwargs},
        )
        return response.choices[0].message.content
