# core/costing.py
"""Estimate USD cost from LLM token usage.

No imports from core/models.py or core/storage.py — self-contained.

Pricing: (prompt_cost_per_1k_tokens, completion_cost_per_1k_tokens) in USD.
Source: provider pricing pages as of 2025-Q1; update as rates change.
"""

from __future__ import annotations

# {provider: {model: (prompt_$/1k, completion_$/1k)}}
# provider keys match LLMCompletion.provider / litellm custom_llm_provider
# model keys match LLMCompletion.model (as returned by litellm)
PRICING_TABLE: dict[str, dict[str, tuple[float, float]]] = {
    "openai": {
        "gpt-4o":           (0.0025, 0.0100),
        "gpt-4o-mini":      (0.00015, 0.0006),  # $0.150/$0.600 per 1M → /1k
        "gpt-4-turbo":      (0.0100, 0.0300),
        "gpt-3.5-turbo":    (0.0005, 0.0015),
    },
    "anthropic": {
        "claude-3-5-sonnet-20241022": (0.0030, 0.0150),
        "claude-3-5-sonnet":          (0.0030, 0.0150),  # alias w/o date suffix
        "claude-3-5-haiku-20241022":  (0.0008, 0.0040),
        "claude-3-5-haiku":           (0.0008, 0.0040),
        "claude-3-opus-20240229":     (0.0150, 0.0750),
        "claude-3-opus":              (0.0150, 0.0750),
    },
    "google": {
        "gemini-1.5-pro":   (0.0035, 0.0105),
        "gemini-1.5-flash":  (0.00035, 0.00105),
    },
}


def estimate_cost(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float | None:
    """Return estimated USD cost for a completion, or None if not in table.

    Args:
        provider: LLM provider string (e.g. "openai", "anthropic", "google").
                  Matched case-insensitively against PRICING_TABLE keys.
        model:    Model identifier as returned by LiteLLMAdapter (e.g. "gpt-4o").
                  Matched case-insensitively; date suffixes are tried first, then
                  a bare-name fallback for convenience.
        prompt_tokens:     Number of prompt/input tokens consumed.
        completion_tokens: Number of completion/output tokens consumed.

    Returns:
        Estimated cost in USD as a float, or None when provider/model is unknown.
    """
    provider_key = provider.lower() if provider else ""
    model_key = model.lower() if model else ""

    models = PRICING_TABLE.get(provider_key)
    if models is None:
        return None

    pricing = models.get(model_key)
    if pricing is None:
        return None

    prompt_cost, completion_cost = pricing
    return (prompt_tokens / 1_000.0) * prompt_cost + (
        completion_tokens / 1_000.0
    ) * completion_cost
