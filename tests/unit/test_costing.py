# tests/unit/test_costing.py
"""T-0120: estimate_cost() correctness for all providers in PRICING_TABLE."""
from __future__ import annotations

import pytest

from core.costing import PRICING_TABLE, estimate_cost


# ---------------------------------------------------------------------------
# Known provider/model → expected USD estimates
# ---------------------------------------------------------------------------


class TestOpenAI:
    def test_gpt4o_mini(self):
        # prompt: 1000 tokens * $0.00015/1k = $0.00015
        # completion: 500 tokens * $0.0006/1k = $0.0003
        cost = estimate_cost("openai", "gpt-4o-mini", 1000, 500)
        assert cost == pytest.approx(0.00045)

    def test_gpt4o_mini_prompt_price_matches_openai_pricing_page(self):
        """Regression: PRICING_TABLE entry must reflect $0.150 per 1M input tokens.

        OpenAI publishes gpt-4o-mini at $0.150 per 1M input tokens. Converted
        to per-1k tokens (our table's unit), that is $0.00015. A previous
        revision had this entry at $0.0001 (= $0.10/1k = $100/1M), wildly
        over-pricing inputs. Cross-check with gpt-4o, which sits at $2.50/1M
        = $0.0025/1k and matches OpenAI's published rate.
        """
        from core.costing import PRICING_TABLE

        prompt_rate, completion_rate = PRICING_TABLE["openai"]["gpt-4o-mini"]
        assert prompt_rate == pytest.approx(0.00015)
        assert completion_rate == pytest.approx(0.0006)

    def test_gpt4o(self):
        # prompt: 2000 * 0.0025/1k = 0.005
        # completion: 1000 * 0.010/1k = 0.010
        cost = estimate_cost("openai", "gpt-4o", 2000, 1000)
        assert cost == pytest.approx(0.015)

    def test_gpt4_turbo(self):
        # prompt: 500 * 0.010/1k = 0.005
        # completion: 200 * 0.030/1k = 0.006
        cost = estimate_cost("openai", "gpt-4-turbo", 500, 200)
        assert cost == pytest.approx(0.011)

    def test_gpt35_turbo(self):
        # prompt: 4000 * 0.0005/1k = 0.002
        # completion: 1000 * 0.0015/1k = 0.0015
        cost = estimate_cost("openai", "gpt-3.5-turbo", 4000, 1000)
        assert cost == pytest.approx(0.0035)


class TestAnthropic:
    def test_claude_3_5_sonnet_with_date(self):
        # prompt: 1000 * 0.003/1k = 0.003
        # completion: 500 * 0.015/1k = 0.0075
        cost = estimate_cost(
            "anthropic", "claude-3-5-sonnet-20241022", 1000, 500
        )
        assert cost == pytest.approx(0.0105)

    def test_claude_3_5_sonnet_alias(self):
        """Alias without date suffix matches same pricing."""
        cost_alias = estimate_cost("anthropic", "claude-3-5-sonnet", 1000, 500)
        cost_full = estimate_cost(
            "anthropic", "claude-3-5-sonnet-20241022", 1000, 500
        )
        assert cost_alias == pytest.approx(cost_full)

    def test_claude_3_5_haiku(self):
        # prompt: 1000 * 0.0008/1k = 0.0008
        # completion: 500 * 0.004/1k = 0.002
        cost = estimate_cost("anthropic", "claude-3-5-haiku", 1000, 500)
        assert cost == pytest.approx(0.0028)

    def test_claude_3_opus(self):
        # prompt: 100 * 0.015/1k = 0.0015
        # completion: 50 * 0.075/1k = 0.00375
        cost = estimate_cost("anthropic", "claude-3-opus", 100, 50)
        assert cost == pytest.approx(0.00525)


class TestGoogle:
    def test_gemini_1_5_pro(self):
        # prompt: 2000 * 0.0035/1k = 0.007
        # completion: 1000 * 0.0105/1k = 0.0105
        cost = estimate_cost("google", "gemini-1.5-pro", 2000, 1000)
        assert cost == pytest.approx(0.0175)

    def test_gemini_1_5_flash(self):
        # prompt: 10000 * 0.00035/1k = 0.0035
        # completion: 5000 * 0.00105/1k = 0.00525
        cost = estimate_cost("google", "gemini-1.5-flash", 10000, 5000)
        assert cost == pytest.approx(0.00875)


# ---------------------------------------------------------------------------
# Unknown provider / unknown model
# ---------------------------------------------------------------------------


def test_unknown_provider_returns_none():
    cost = estimate_cost("cohere", "command-r", 1000, 500)
    assert cost is None


def test_unknown_model_known_provider_returns_none():
    cost = estimate_cost("openai", "gpt-99-ultra", 1000, 500)
    assert cost is None


def test_unknown_model_anthropic_returns_none():
    cost = estimate_cost("anthropic", "claude-9000", 100, 50)
    assert cost is None


def test_empty_provider_returns_none():
    cost = estimate_cost("", "gpt-4o-mini", 1000, 500)
    assert cost is None


def test_empty_model_returns_none():
    cost = estimate_cost("openai", "", 1000, 500)
    assert cost is None


# ---------------------------------------------------------------------------
# Case-insensitivity
# ---------------------------------------------------------------------------


def test_provider_case_insensitive():
    cost_lower = estimate_cost("openai", "gpt-4o-mini", 1000, 500)
    cost_upper = estimate_cost("OpenAI", "gpt-4o-mini", 1000, 500)
    assert cost_lower == pytest.approx(cost_upper)


def test_model_case_insensitive():
    cost_lower = estimate_cost("openai", "gpt-4o-mini", 1000, 500)
    cost_upper = estimate_cost("openai", "GPT-4O-MINI", 1000, 500)
    assert cost_lower == pytest.approx(cost_upper)


# ---------------------------------------------------------------------------
# Zero tokens
# ---------------------------------------------------------------------------


def test_zero_tokens_returns_zero():
    cost = estimate_cost("openai", "gpt-4o-mini", 0, 0)
    assert cost == pytest.approx(0.0)


def test_zero_prompt_tokens():
    cost = estimate_cost("openai", "gpt-4o-mini", 0, 1000)
    expected = (1000 / 1000.0) * 0.0006
    assert cost == pytest.approx(expected)


def test_zero_completion_tokens():
    cost = estimate_cost("openai", "gpt-4o-mini", 1000, 0)
    expected = (1000 / 1000.0) * 0.00015
    assert cost == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_deterministic_same_inputs():
    """Same inputs always produce same output."""
    results = [
        estimate_cost("anthropic", "claude-3-5-sonnet", 500, 250)
        for _ in range(10)
    ]
    assert all(r == results[0] for r in results)


def test_deterministic_across_providers():
    """Different providers with same token counts return independent values."""
    c1 = estimate_cost("openai", "gpt-4o-mini", 1000, 500)
    c2 = estimate_cost("anthropic", "claude-3-5-haiku", 1000, 500)
    # Both should be deterministic but different
    assert c1 == pytest.approx(estimate_cost("openai", "gpt-4o-mini", 1000, 500))
    assert c2 == pytest.approx(estimate_cost("anthropic", "claude-3-5-haiku", 1000, 500))
    assert c1 != pytest.approx(c2)


# ---------------------------------------------------------------------------
# PRICING_TABLE structure sanity
# ---------------------------------------------------------------------------


def test_pricing_table_all_providers_have_models():
    for provider, models in PRICING_TABLE.items():
        assert len(models) > 0, f"Provider {provider!r} has no models"


def test_pricing_table_all_rates_positive():
    for provider, models in PRICING_TABLE.items():
        for model, (prompt_rate, completion_rate) in models.items():
            assert prompt_rate > 0, f"{provider}/{model} prompt rate not positive"
            assert completion_rate > 0, f"{provider}/{model} completion rate not positive"
