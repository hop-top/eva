# tests/e2e/test_forbidden_phrases_evaluator.py
"""E2E: forbidden_phrases evaluator (US-040, T-0300).

One test per acceptance bullet on
docs/stories/US-040-forbidden-phrases-evaluator.md.
"""
from __future__ import annotations

from core.evaluators.forbidden_phrases import ForbiddenPhrasesEvaluator
from core.models import Score


# ---------------------------------------------------------------------------
# basic hit / miss
# ---------------------------------------------------------------------------

def test_fail_when_banned_phrase_present():
    ev = ForbiddenPhrasesEvaluator(banlist=["delve", "tapestry"])
    score = ev.run("We delve into the data.")
    assert isinstance(score, Score)
    assert score.value == 0.0
    assert score.reason is not None
    assert "delve" in score.reason


def test_pass_when_no_banned_phrase():
    ev = ForbiddenPhrasesEvaluator(banlist=["delve", "tapestry"])
    score = ev.run("We explore the data.")
    assert score.value == 1.0


# ---------------------------------------------------------------------------
# empty banlist always passes
# ---------------------------------------------------------------------------

def test_empty_banlist_always_passes():
    ev = ForbiddenPhrasesEvaluator(banlist=[])
    score = ev.run("anything goes here — delve all you want")
    assert score.value == 1.0


# ---------------------------------------------------------------------------
# case-insensitive default
# ---------------------------------------------------------------------------

def test_case_insensitive_default():
    ev = ForbiddenPhrasesEvaluator(banlist=["DELVE"])
    score = ev.run("we delve here")
    assert score.value == 0.0


# ---------------------------------------------------------------------------
# whole-word default
# ---------------------------------------------------------------------------

def test_whole_word_default_does_not_fire_on_substring():
    ev = ForbiddenPhrasesEvaluator(banlist=["cat"])
    score = ev.run("concatenate strings carefully")
    assert score.value == 1.0


# ---------------------------------------------------------------------------
# whole_word=False enables substring matches
# ---------------------------------------------------------------------------

def test_substring_match_when_whole_word_false():
    ev = ForbiddenPhrasesEvaluator(banlist=["cat"], whole_word=False)
    score = ev.run("concatenate")
    assert score.value == 0.0


# ---------------------------------------------------------------------------
# multi-word phrase
# ---------------------------------------------------------------------------

def test_multi_word_phrase_match():
    ev = ForbiddenPhrasesEvaluator(banlist=["in the realm of"])
    score = ev.run("In the realm of AI, ...")
    assert score.value == 0.0


# ---------------------------------------------------------------------------
# multi-hit reason summary
# ---------------------------------------------------------------------------

def test_multiple_hits_summarised_in_reason():
    banlist = ["alpha", "beta", "gamma", "delta", "epsilon"]
    ev = ForbiddenPhrasesEvaluator(banlist=banlist)
    score = ev.run("alpha beta gamma delta epsilon all appear here")
    assert score.value == 0.0
    assert score.reason is not None
    # Top-3 shown, "+2 more" suffix.
    assert "alpha" in score.reason
    assert "more" in score.reason
