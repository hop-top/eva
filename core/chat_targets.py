# core/chat_targets.py
"""Provider-agnostic chat targets for dataset mode.

A dataset ``target:`` may be a mapping instead of a URL::

    target:
      provider: openai            # openai | anthropic (pluggable)
      base_url: http://localhost:12000/v1
      model: my-local-model
      api_key_env: MY_KEY_ENV     # optional; env var NAME, never the key
      max_tokens: 2048
      temperature: 0.0
      top_p: 1.0
      timeout_s: 120

Field names match hop-top/ben endpoint configs so they are portable.

Providers register in ``CHAT_PROVIDERS`` (name -> ChatProvider subclass).
Each turns a ChatTarget + prompt into a ChatResult: the answer text only,
reasoning separated, plus model id / usage / latency for the run store.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, ClassVar

import httpx
from pydantic import BaseModel, ConfigDict


class TargetError(RuntimeError):
    """Target call failed (transport, HTTP status, malformed body).

    The runner records this as an ``upstream_error`` case instead of
    aborting the whole run.
    """


class ChatTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str
    base_url: str | None = None
    api_key_env: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    timeout_s: float = 120.0
    system: str | None = None  # optional system prompt (eva addition)

    @property
    def resolved_base_url(self) -> str:
        if self.base_url:
            return self.base_url.rstrip("/")
        cls = CHAT_PROVIDERS.get(self.provider)
        return cls.default_base_url if cls else ""

    @property
    def label(self) -> str:
        """Stable string stored as Run.target; keys runs for list/compare/drift."""
        return f"{self.provider}:{self.model}@{self.resolved_base_url}"


@dataclass
class ChatToolCall:
    """One tool call returned by the model (never executed).

    ``args`` is the parsed argument object. When the model's arguments are
    not a valid JSON object, ``args`` is ``{}`` and ``raw_args`` holds the
    original string; otherwise ``raw_args`` is None.
    """

    name: str
    args: dict[str, Any] = field(default_factory=dict)
    raw_args: str | None = None


def parse_tool_arguments(raw: Any) -> tuple[dict[str, Any], str | None]:
    """Parse an OpenAI-style ``function.arguments`` value -> (args, raw_args)."""
    if isinstance(raw, dict):  # some servers return an object, not a string
        return raw, None
    if not isinstance(raw, str):
        return {}, None if raw is None else str(raw)
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {}, raw
    if isinstance(parsed, dict):
        return parsed, None
    return {}, raw


@dataclass
class ChatResult:
    """Answer + metadata from one chat call."""

    text: str
    reasoning: str | None = None
    provider: str | None = None
    model: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    latency_ms: int | None = None
    finish_reason: str | None = None
    tool_calls: list[ChatToolCall] = field(default_factory=list)


_THINK_RE = re.compile(r"<think(?:ing)?>(.*?)</think(?:ing)?>", re.DOTALL | re.IGNORECASE)
_THINK_CLOSE_RE = re.compile(r"</think(?:ing)?>", re.IGNORECASE)


def split_reasoning(content: str) -> tuple[str, str | None]:
    """Split inline ``<think>…</think>`` reasoning from the answer.

    Handles complete blocks and the common "opening tag stripped by the
    chat template" shape (``reasoning…</think>answer``). Returns
    ``(answer, reasoning_or_None)``.
    """
    parts = [m.group(1).strip() for m in _THINK_RE.finditer(content)]
    answer = _THINK_RE.sub("", content)
    closes = list(_THINK_CLOSE_RE.finditer(answer))
    if closes:
        last = closes[-1]
        parts.append(answer[: closes[0].start()].strip())
        answer = answer[last.end():]
    reasoning = "\n\n".join(p for p in parts if p) or None
    return answer.strip(), reasoning


def _int(v: Any) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) else None


class ChatProvider:
    name: ClassVar[str]
    default_base_url: ClassVar[str] = ""

    def __init__(self, target: ChatTarget):
        self.target = target

    def api_key(self) -> str | None:
        env = self.target.api_key_env
        if not env:
            return None
        key = os.environ.get(env)
        if not key:
            raise TargetError(f"api_key_env {env!r} is not set in the environment")
        return key

    def build_request(
        self,
        prompt: str,
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
    ) -> tuple[str, dict[str, str], dict]:
        raise NotImplementedError

    def parse_response(self, body: dict) -> ChatResult:
        raise NotImplementedError

    async def complete(
        self,
        prompt: str,
        client: httpx.AsyncClient | None = None,
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
    ) -> ChatResult:
        if tools or tool_choice is not None:
            url, headers, payload = self.build_request(
                prompt, tools=tools, tool_choice=tool_choice
            )
        else:
            url, headers, payload = self.build_request(prompt)
        t0 = time.perf_counter()
        try:
            if client is not None:
                resp = await client.post(url, headers=headers, json=payload)
            else:
                async with httpx.AsyncClient(timeout=self.target.timeout_s) as c:
                    resp = await c.post(url, headers=headers, json=payload)
        except httpx.HTTPError as e:
            raise TargetError(f"{type(e).__name__}: {e}") from e
        latency_ms = int((time.perf_counter() - t0) * 1000)
        if resp.status_code >= 400:
            raise TargetError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        try:
            body = resp.json()
            result = self.parse_response(body)
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise TargetError(
                f"malformed {self.name} response ({type(e).__name__}: {e}): "
                f"{resp.text[:200]}"
            ) from e
        result.provider = self.name
        result.model = result.model or self.target.model
        result.latency_ms = latency_ms
        return result


class OpenAIProvider(ChatProvider):
    """OpenAI-compatible ``POST {base_url}/chat/completions``.

    Works with OpenAI, mlx_lm.server, Ollama ``/v1``, vLLM. No auth header
    unless ``api_key_env`` names a set env var (a key is never guessed from
    ``OPENAI_API_KEY``, so local servers never see it).
    """

    name = "openai"
    default_base_url = "https://api.openai.com/v1"

    def build_request(self, prompt: str, tools=None, tool_choice=None):
        t = self.target
        messages = []
        if t.system:
            messages.append({"role": "system", "content": t.system})
        messages.append({"role": "user", "content": prompt})
        payload: dict[str, Any] = {"model": t.model, "messages": messages}
        if t.max_tokens is not None:
            payload["max_tokens"] = t.max_tokens
        if t.temperature is not None:
            payload["temperature"] = t.temperature
        if t.top_p is not None:
            payload["top_p"] = t.top_p
        if tools:
            payload["tools"] = tools
            if tool_choice is not None:
                payload["tool_choice"] = tool_choice
        headers = {"Content-Type": "application/json"}
        key = self.api_key()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return f"{t.resolved_base_url}/chat/completions", headers, payload

    def parse_response(self, body: dict) -> ChatResult:
        choice = body["choices"][0]
        message = choice["message"]
        content = message.get("content") or ""
        reasoning = message.get("reasoning_content") or message.get("reasoning")
        answer, inline = split_reasoning(content)
        if inline:
            reasoning = f"{reasoning}\n\n{inline}" if reasoning else inline
        calls: list[ChatToolCall] = []
        for tc in message.get("tool_calls") or []:
            fn = tc.get("function") or {}
            args, raw = parse_tool_arguments(fn.get("arguments"))
            calls.append(ChatToolCall(
                name=fn.get("name") or "", args=args, raw_args=raw
            ))
        usage_in = body.get("usage") or {}
        usage = {
            k: v
            for k in ("prompt_tokens", "completion_tokens", "total_tokens")
            if (v := _int(usage_in.get(k))) is not None
        }
        return ChatResult(
            text=answer,
            reasoning=reasoning or None,
            model=body.get("model"),
            usage=usage,
            finish_reason=choice.get("finish_reason"),
            tool_calls=calls,
        )


class AnthropicProvider(ChatProvider):
    """Anthropic Messages API.

    ``base_url`` may be the host (``https://api.anthropic.com``), a ``/v1``
    root, or the full ``…/v1/messages`` URL. Key comes from ``api_key_env``,
    default ``ANTHROPIC_API_KEY``.
    """

    name = "anthropic"
    default_base_url = "https://api.anthropic.com"
    api_version = "2023-06-01"
    default_max_tokens = 4096

    def _url(self) -> str:
        base = self.target.resolved_base_url
        if base.endswith("/messages"):
            return base
        if base.endswith("/v1"):
            return f"{base}/messages"
        return f"{base}/v1/messages"

    def api_key(self) -> str | None:
        env = self.target.api_key_env or "ANTHROPIC_API_KEY"
        key = os.environ.get(env)
        if not key:
            raise TargetError(f"api key env {env!r} is not set in the environment")
        return key

    @staticmethod
    def _translate_tools(tools: list[dict]) -> list[dict]:
        out = []
        for tool in tools:
            fn = tool.get("function") or tool
            entry: dict[str, Any] = {
                "name": fn.get("name"),
                "input_schema": fn.get("parameters")
                or {"type": "object", "properties": {}},
            }
            if fn.get("description"):
                entry["description"] = fn["description"]
            out.append(entry)
        return out

    @staticmethod
    def _translate_tool_choice(choice: str | dict) -> dict:
        if isinstance(choice, dict):
            name = (choice.get("function") or {}).get("name") or choice.get("name")
            if name:
                return {"type": "tool", "name": name}
            return choice
        return {"type": {"required": "any"}.get(choice, choice)}

    def build_request(self, prompt: str, tools=None, tool_choice=None):
        t = self.target
        payload: dict[str, Any] = {
            "model": t.model,
            "max_tokens": t.max_tokens or self.default_max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if t.system:
            payload["system"] = t.system
        if t.temperature is not None:
            payload["temperature"] = t.temperature
        if t.top_p is not None:
            payload["top_p"] = t.top_p
        if tools:
            payload["tools"] = self._translate_tools(tools)
            if tool_choice is not None:
                payload["tool_choice"] = self._translate_tool_choice(tool_choice)
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key() or "",
            "anthropic-version": self.api_version,
        }
        return self._url(), headers, payload

    def parse_response(self, body: dict) -> ChatResult:
        texts: list[str] = []
        thoughts: list[str] = []
        calls: list[ChatToolCall] = []
        for block in body["content"]:
            kind = block.get("type")
            if kind == "text":
                texts.append(block.get("text", ""))
            elif kind == "thinking":
                thoughts.append(block.get("thinking", ""))
            elif kind == "tool_use":
                args = block.get("input")
                calls.append(ChatToolCall(
                    name=block.get("name") or "",
                    args=args if isinstance(args, dict) else {},
                ))
        answer, inline = split_reasoning("".join(texts))
        if inline:
            thoughts.append(inline)
        usage_in = body.get("usage") or {}
        inp, out = _int(usage_in.get("input_tokens")), _int(usage_in.get("output_tokens"))
        usage: dict[str, int] = {}
        if inp is not None:
            usage["prompt_tokens"] = inp
        if out is not None:
            usage["completion_tokens"] = out
        if inp is not None and out is not None:
            usage["total_tokens"] = inp + out
        return ChatResult(
            text=answer,
            reasoning="\n\n".join(t for t in thoughts if t) or None,
            model=body.get("model"),
            usage=usage,
            finish_reason=body.get("stop_reason"),
            tool_calls=calls,
        )


CHAT_PROVIDERS: dict[str, type[ChatProvider]] = {
    OpenAIProvider.name: OpenAIProvider,
    AnthropicProvider.name: AnthropicProvider,
}


def register_chat_provider(cls: type[ChatProvider]) -> type[ChatProvider]:
    """Register a custom provider (usable as a decorator)."""
    CHAT_PROVIDERS[cls.name] = cls
    return cls


def build_provider(target: ChatTarget) -> ChatProvider:
    cls = CHAT_PROVIDERS.get(target.provider)
    if cls is None:
        raise ValueError(
            f"unknown chat provider {target.provider!r}; "
            f"known: {', '.join(sorted(CHAT_PROVIDERS))}"
        )
    return cls(target)
