# tests/unit/test_prose_assertion.py
"""Unit tests for the prose-assertion evaluator.

Covers:
- rule matcher (per-pattern + ≥80% coverage on cc-skills conventional-git corpus)
- cache determinism (same input → same key → same plan)
- llm_judge fallback path (mocked LLM)
- negation semantics (does NOT contain X)
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.evaluators.prose_assertion import (
    JUDGE_MODEL,
    JUDGE_TEMPERATURE,
    RULESET_VERSION,
    EvaluatorPlan,
    ProseAssertionEvaluator,
    _cache_key,
    cache_load,
    cache_store,
    match_assertion,
)
from core.models import Score


# ---------------------------------------------------------------------------
# Cache isolation: redirect XDG_STATE_HOME to a tmp dir for every test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    yield tmp_path


# ---------------------------------------------------------------------------
# Rule matcher — per-pattern coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "assertion,expected_eval,expected_negate",
    [
        # negated contains
        ("branch name does NOT contain 'worktree'", "contains", True),
        ("response does not contain 'AI signature'", "contains", True),
        ("subject line does not contain '#42'", "contains", True),
        ("must not contain 'foo'", "contains", True),
        # positive contains
        ("response contains 'refund'", "contains", False),
        ("includes the word 'closes'", "contains", False),
        ("body contains 'This reverts commit'", "contains", False),
        # starts with
        ("branch name starts with 'feat/'", "regex", False),
        ("description begins with 'add'", "regex", False),
        # ends with
        ("subject line ends with '.'", "regex", False),
        # word/char counts
        ("response is at most 50 words", "word_count", False),
        ("response is ≤ 50 words", "word_count", False),
        ("description is 50 characters or fewer", "regex", False),
        ("subject line is at most 72 chars", "regex", False),
        # regex/pattern
        ("matches pattern '^feat/'", "regex", False),
        ("matches regex 'v\\d+'", "regex", False),
    ],
)
def test_match_assertion_dispatches_correctly(assertion, expected_eval, expected_negate):
    plan = match_assertion(assertion)
    assert plan is not None, f"expected match for: {assertion}"
    assert plan.evaluator == expected_eval
    assert plan.negate == expected_negate


def test_match_assertion_returns_none_on_unmatched():
    # Mood assertions are out of scope until MoodEvaluator lands.
    assert match_assertion("uses imperative mood") is None
    assert match_assertion("uses past tense") is None
    # Free-form judgement assertions also fall through.
    assert match_assertion("response is well-written and concise") is None
    assert match_assertion("explains the rationale clearly") is None


# ---------------------------------------------------------------------------
# Negation runtime behaviour
# ---------------------------------------------------------------------------


def test_negated_contains_passes_when_substring_absent():
    ev = ProseAssertionEvaluator("branch name does NOT contain 'worktree'")
    score = ev.run("feat/oauth-login")
    assert score.value == 1.0


def test_negated_contains_fails_when_substring_present():
    ev = ProseAssertionEvaluator("branch name does NOT contain 'worktree'")
    score = ev.run("feat/worktree-oauth-login")
    assert score.value == 0.0
    assert "negated" in (score.reason or "").lower() or "worktree" in (score.reason or "")


def test_positive_contains_passes_when_substring_present():
    ev = ProseAssertionEvaluator("response contains 'refund'")
    score = ev.run("Your refund has been processed.")
    assert score.value == 1.0


def test_starts_with_passes_when_prefix_present():
    ev = ProseAssertionEvaluator("branch name starts with 'feat/'")
    score = ev.run("feat/oauth-login")
    assert score.value == 1.0


def test_starts_with_fails_when_prefix_absent():
    ev = ProseAssertionEvaluator("branch name starts with 'feat/'")
    score = ev.run("fix/login-bug")
    assert score.value == 0.0


def test_max_words_passes_under_limit():
    ev = ProseAssertionEvaluator("response is at most 10 words")
    score = ev.run("short and sweet")
    assert score.value == 1.0


def test_max_words_fails_over_limit():
    ev = ProseAssertionEvaluator("response is at most 5 words")
    score = ev.run("this response has more than five words clearly")
    assert score.value == 0.0


def test_max_chars_routes_to_regex_and_passes():
    ev = ProseAssertionEvaluator("description is at most 50 chars")
    score = ev.run("short description here")
    assert score.value == 1.0


def test_max_chars_fails_over_limit():
    ev = ProseAssertionEvaluator("description is at most 5 chars")
    score = ev.run("way too long for five")
    assert score.value == 0.0


def test_matches_pattern_passes():
    ev = ProseAssertionEvaluator("matches pattern '^feat/'")
    score = ev.run("feat/anything")
    assert score.value == 1.0


# ---------------------------------------------------------------------------
# Cache — determinism + key stability + invalidation on ruleset bump
# ---------------------------------------------------------------------------


def test_cache_key_deterministic_across_calls():
    a = _cache_key("response contains 'x'")
    b = _cache_key("response contains 'x'")
    assert a == b


def test_cache_key_changes_with_ruleset_version():
    a = _cache_key("response contains 'x'", ruleset_version=1)
    b = _cache_key("response contains 'x'", ruleset_version=2)
    assert a != b


def test_cache_load_miss_returns_none():
    assert cache_load("nothing cached yet") is None


def test_cache_store_then_load_round_trip(tmp_path):
    plan = EvaluatorPlan(
        evaluator="contains",
        config={"substring": "x", "case_sensitive": False},
        negate=True,
    )
    cache_store("an assertion", plan)
    loaded = cache_load("an assertion")
    assert loaded == plan


def test_cache_hit_is_used_on_second_compile(monkeypatch):
    """If the matcher is bypassed (cache hit), the second compile must
    return the cached plan, not re-run the matcher."""
    # Prime the cache with a hand-crafted plan that the matcher would never
    # produce naturally. If the second compile re-matches, the plan will
    # change shape.
    custom = EvaluatorPlan(
        evaluator="contains",
        config={"substring": "sentinel", "case_sensitive": True},
        negate=False,
    )
    cache_store("response contains 'refund'", custom)

    ev = ProseAssertionEvaluator("response contains 'refund'")
    # On cache HIT, the plan equals our sentinel — proving the matcher was skipped.
    assert ev.plan == custom


def test_two_evaluators_same_assertion_share_plan():
    ev1 = ProseAssertionEvaluator("branch name starts with 'feat/'")
    ev2 = ProseAssertionEvaluator("branch name starts with 'feat/'")
    assert ev1.plan == ev2.plan


def test_cache_invalidated_by_bumping_ruleset_version(monkeypatch):
    # Write a plan under version 1
    plan_v1 = EvaluatorPlan(evaluator="contains", config={"substring": "x"}, negate=False)
    cache_store("assertion text", plan_v1, ruleset_version=1)
    # Reading at the same version returns the plan
    assert cache_load("assertion text", ruleset_version=1) == plan_v1
    # But at version 2 it's a miss (different key)
    assert cache_load("assertion text", ruleset_version=2) is None


# ---------------------------------------------------------------------------
# llm_judge fallback path (mocked)
# ---------------------------------------------------------------------------


def _make_mock_llm(reply: str) -> MagicMock:
    """Mock LiteLLMAdapter — async complete() returns a completion with `reply`."""
    mock = MagicMock()
    completion = MagicMock()
    completion.content = reply
    mock.complete = AsyncMock(return_value=completion)
    return mock


def test_unmatched_assertion_falls_through_to_llm_judge_plan():
    ev = ProseAssertionEvaluator(
        "uses imperative mood",
        llm_adapter=_make_mock_llm("1.0\nImperative."),
    )
    assert ev.plan.evaluator == "llm_judge"
    assert ev.plan.config["assertion"] == "uses imperative mood"


def test_llm_judge_fallback_passes():
    llm = _make_mock_llm("1.0\nImperative mood detected.")
    ev = ProseAssertionEvaluator("uses imperative mood", llm_adapter=llm)
    score = ev.run("add user authentication")
    assert score.value == 1.0
    assert score.metadata["judge_model"] == JUDGE_MODEL
    assert score.metadata["judge_temperature"] == JUDGE_TEMPERATURE


def test_llm_judge_fallback_fails():
    llm = _make_mock_llm("0.0\nPast tense detected.")
    ev = ProseAssertionEvaluator("uses imperative mood", llm_adapter=llm)
    score = ev.run("added user authentication")
    assert score.value == 0.0


def test_llm_judge_passes_pinned_temperature():
    llm = _make_mock_llm("1.0\n")
    ev = ProseAssertionEvaluator("uses imperative mood", llm_adapter=llm)
    ev.run("anything")
    # First positional arg = messages, second kwarg = temperature
    call = llm.complete.call_args
    assert call.kwargs.get("temperature") == JUDGE_TEMPERATURE


def test_llm_judge_without_adapter_raises():
    ev = ProseAssertionEvaluator("uses imperative mood")  # no llm_adapter
    with pytest.raises(ValueError, match="llm_adapter"):
        ev.run("anything")


# ---------------------------------------------------------------------------
# Coverage benchmark: ≥80% of cc-skills conventional-git assertions
# route to a programmatic evaluator (not llm_judge).
# ---------------------------------------------------------------------------


# Curated subset of cc-skills conventional-git assertion phrasings. Drawn
# from /Users/jadb/.p/sandbox/cc-skills/skills/conventional-git/evals/evals.json
# and rephrased to canonical surface forms. Each entry: (assertion, expect_match).
#
# We accept ≥80% match-rate on the rule-matchable subset. The 'expect_match'
# column marks the ones we EXPECT to programmatically route. Items marked
# False are expected to fall through (mood, "explains why", structural
# constraints not yet covered) — they're tracked here so the corpus stays
# honest as the rule table grows.
CC_SKILLS_CORPUS: list[tuple[str, bool]] = [
    # eval 1: branch name
    ("branch name does NOT contain the word 'worktree'", True),
    ("branch name starts with 'feat/'", True),
    ("branch name description part is 50 characters or fewer", True),
    # eval 2: AI attribution
    ("response does not contain 'Co-authored-by: Claude'", True),
    ("response does not contain 'Co-authored-by: Claude Code'", True),
    # eval 3: scope
    ("description starts with 'add'", True),
    # eval 4: PR title squash
    ("response contains 'squash'", True),
    ("response contains 'Conventional Commits'", True),
    # eval 5: footer
    ("subject line does not contain '#42'", True),
    ("body contains 'Closes #42'", True),
    # eval 6: deps type
    ("response contains 'build'", True),
    ("response does not contain 'chore'", True),
    # eval 7: revert
    ("body contains 'This reverts commit'", True),
    ("body contains 'abc1234f'", True),
    # eval 8: breaking change
    ("response contains '!'", True),
    ("response contains 'BREAKING CHANGE'", True),
    # eval 10: closing references
    ("response contains 'Closes #101'", True),
    ("response contains 'Closes #102'", True),
    # Out-of-scope items (mood, narrative). Tracked for honesty.
    ("description uses imperative mood", False),
    ("description uses past tense", False),
    ("explains why worktree should not appear in branch names", False),
]


def test_cc_skills_corpus_coverage_at_least_80_percent():
    """At least 80% of the cc-skills conventional-git assertions route to
    a programmatic evaluator (not llm_judge fallback).

    See CC_SKILLS_CORPUS above for the breakdown. This is the headline
    metric in the rule-matcher acceptance criterion."""
    in_scope = [a for a, expect in CC_SKILLS_CORPUS if expect]
    total = len(CC_SKILLS_CORPUS)
    matched = sum(1 for a in in_scope if match_assertion(a) is not None)
    coverage = matched / total
    assert coverage >= 0.80, (
        f"rule coverage {coverage:.0%} below 80% target "
        f"({matched}/{total} matched). Unmatched in-scope items:\n  "
        + "\n  ".join(a for a in in_scope if match_assertion(a) is None)
    )


def test_cc_skills_corpus_unmatched_items_fall_through():
    """The items we DON'T expect to match (mood, free-form) really do
    return None — guards against accidental over-matching."""
    out_of_scope = [a for a, expect in CC_SKILLS_CORPUS if not expect]
    for a in out_of_scope:
        assert match_assertion(a) is None, (
            f"unexpected match for out-of-scope assertion: {a}"
        )


# ---------------------------------------------------------------------------
# EvaluatorPlan serialisation
# ---------------------------------------------------------------------------


def test_evaluator_plan_round_trip_through_json():
    plan = EvaluatorPlan(
        evaluator="contains",
        config={"substring": "x", "case_sensitive": False},
        negate=True,
    )
    raw = plan.to_json()
    restored = EvaluatorPlan.from_json(raw)
    assert restored == plan


def test_evaluator_plan_json_is_sorted_for_determinism():
    """Two structurally equal plans must serialise to the SAME bytes —
    otherwise cache file contents drift run-to-run."""
    p1 = EvaluatorPlan(evaluator="contains", config={"substring": "x", "case_sensitive": False}, negate=True)
    p2 = EvaluatorPlan(evaluator="contains", config={"case_sensitive": False, "substring": "x"}, negate=True)
    assert p1.to_json() == p2.to_json()


# ---------------------------------------------------------------------------
# Legacy alias
# ---------------------------------------------------------------------------


def test_legacy_underscore_run_alias():
    ev = ProseAssertionEvaluator("response contains 'x'")
    assert ev._run == ev.run


# ---------------------------------------------------------------------------
# T-0380: mode override
# ---------------------------------------------------------------------------


def test_mode_auto_default_routes_programmatic_when_rule_matches():
    """Default mode is auto — known rule wins."""
    ev = ProseAssertionEvaluator("response contains 'foo'")
    assert ev.plan.evaluator == "contains"
    assert ev.mode == "auto"


def test_mode_judge_only_skips_rule_matcher():
    """judge_only forces llm_judge plan even when a rule would match."""
    llm = AsyncMock()
    ev = ProseAssertionEvaluator(
        "response contains 'foo'",
        llm_adapter=llm,
        mode="judge_only",
    )
    assert ev.plan.evaluator == "llm_judge"
    assert ev.mode == "judge_only"


def test_mode_programmatic_only_passes_when_rule_matches():
    """programmatic_only is OK when a rule does match."""
    ev = ProseAssertionEvaluator(
        "response contains 'foo'",
        mode="programmatic_only",
    )
    assert ev.plan.evaluator == "contains"
    assert ev.mode == "programmatic_only"


def test_mode_programmatic_only_raises_when_no_rule_matches():
    """programmatic_only fails at construction when no rule matches.

    Contract authors hear about ambiguous assertions at load, not at run.
    """
    with pytest.raises(ValueError, match="programmatic_only"):
        ProseAssertionEvaluator(
            "convey a sense of optimism",  # not a recognisable rule pattern
            mode="programmatic_only",
        )


def test_mode_unknown_value_rejected():
    with pytest.raises(ValueError, match="unknown prose-assertion mode"):
        ProseAssertionEvaluator("response contains 'x'", mode="invalid_mode")


def test_cache_key_includes_mode_isolation():
    """Same assertion under different modes hashes to different cache keys."""
    a = _cache_key("response contains 'x'", mode="auto")
    j = _cache_key("response contains 'x'", mode="judge_only")
    p = _cache_key("response contains 'x'", mode="programmatic_only")
    assert a != j
    assert a != p
    assert j != p


def test_cache_isolation_between_modes(tmp_path, monkeypatch):
    """Cache entry under auto must not be reused for judge_only.

    Guards against the regression where mode override would silently
    re-route the same assertion via the wrong cached plan.
    """
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    # Compile under auto — caches a `contains` plan.
    ev_auto = ProseAssertionEvaluator("response contains 'x'")
    assert ev_auto.plan.evaluator == "contains"
    # Compile same assertion under judge_only — must NOT see the auto plan;
    # must build a fresh llm_judge plan.
    llm = AsyncMock()
    ev_judge = ProseAssertionEvaluator(
        "response contains 'x'", llm_adapter=llm, mode="judge_only"
    )
    assert ev_judge.plan.evaluator == "llm_judge"


def test_mode_judge_only_uses_pinned_temperature():
    """judge_only path still pins judge temperature (no regression)."""
    completion = MagicMock()
    completion.content = "1.0\nlooks good"
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=completion)
    ev = ProseAssertionEvaluator(
        "response is upbeat",
        llm_adapter=llm,
        mode="judge_only",
    )
    score = ev.run("Hooray!")
    assert score.value == 1.0
    # Confirm pinned temperature was passed
    _, kwargs = llm.complete.call_args
    assert kwargs.get("temperature") == JUDGE_TEMPERATURE
