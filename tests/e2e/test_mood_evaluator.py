# tests/e2e/test_mood_evaluator.py
"""E2E: mood evaluator (US-038, T-0296).

One test per acceptance bullet on docs/stories/US-038-mood-evaluator.md.
Programmatic Tier-1 — no LLM, no subprocess.
"""
from __future__ import annotations

import pytest

from core.evaluators.mood import MoodEvaluator
from core.models import Score


# ---------------------------------------------------------------------------
# imperative
# ---------------------------------------------------------------------------

def test_imperative_pass_when_dominant():
    """`expected=imperative` passes when sentences begin with imperative verbs."""
    ev = MoodEvaluator(expected="imperative")
    score = ev.run("Open the file. Save it. Commit the change.")
    assert isinstance(score, Score)
    assert score.value == 1.0


# ---------------------------------------------------------------------------
# past
# ---------------------------------------------------------------------------

def test_past_pass_when_dominant():
    """`expected=past` passes for predominantly past-tense response."""
    ev = MoodEvaluator(expected="past")
    score = ev.run("We shipped the feature. The team reviewed the PR. It worked.")
    assert score.value == 1.0


def test_past_fail_when_present_tense():
    """Equivalent-length present-tense response scores 0.0 against expected=past."""
    ev = MoodEvaluator(expected="past")
    score = ev.run("Open the file. Save it. Commit the change.")
    assert score.value == 0.0


# ---------------------------------------------------------------------------
# passive
# ---------------------------------------------------------------------------

def test_passive_pass_when_dominant():
    """`expected=passive` passes when be-form + past participle dominates."""
    ev = MoodEvaluator(expected="passive")
    score = ev.run("The file was saved. The commit was pushed. The PR was merged.")
    assert score.value == 1.0


# ---------------------------------------------------------------------------
# first-person
# ---------------------------------------------------------------------------

def test_first_person_pass_when_dominant():
    """`expected=first_person` passes when I/we/my/our appear in most sentences."""
    ev = MoodEvaluator(expected="first_person")
    score = ev.run("I shipped my feature today. We reviewed our PR. My team is happy.")
    assert score.value == 1.0


# ---------------------------------------------------------------------------
# failure reason / shape
# ---------------------------------------------------------------------------

def test_failure_reason_names_mismatch():
    """Score reason names dominant mood vs expected when failing."""
    ev = MoodEvaluator(expected="imperative")
    score = ev.run("We shipped the feature. The team reviewed the PR. It worked.")
    assert score.value == 0.0
    assert score.reason is not None
    # Either "no imperative sentences detected" (n=0 path) or
    # "dominant mood ... != expected imperative" (n>0 path) is acceptable.
    assert ("imperative" in score.reason) and ("expected" in score.reason or "no " in score.reason)


# ---------------------------------------------------------------------------
# empty / whitespace
# ---------------------------------------------------------------------------

def test_empty_response_scores_zero_no_crash():
    """Empty response returns 0.0 with reason; does not crash."""
    ev = MoodEvaluator(expected="imperative")
    score = ev.run("")
    assert score.value == 0.0
    assert score.reason is not None


def test_whitespace_only_response_scores_zero_no_crash():
    ev = MoodEvaluator(expected="past")
    score = ev.run("   \n  \t  ")
    assert score.value == 0.0


# ---------------------------------------------------------------------------
# config validation
# ---------------------------------------------------------------------------

def test_unsupported_expected_raises_value_error():
    """Constructing with an unsupported `expected` raises ValueError."""
    with pytest.raises(ValueError):
        MoodEvaluator(expected="subjunctive")
