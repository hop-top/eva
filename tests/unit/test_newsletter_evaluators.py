# tests/unit/test_newsletter_evaluators.py
"""Unit tests for newsletter pack evaluators (T-0201, US-037).

Two new Tier-1 deterministic evaluators back the newsletter pack:
- word_count: max-words gate; fails responses longer than `max`.
- last_paragraph_regex: regex over the final paragraph only (CTA gate).

The other two pack contracts (no-hallucinations + style) are composed
from the existing `regex` built-in — covered by tests/e2e/test_newsletter_contracts.py.
"""
import pytest

from core.evaluators import EVALUATOR_REGISTRY
from core.evaluators.builtin import BUILTIN_EVALUATOR_FACTORIES
from core.evaluators.last_paragraph_regex import LastParagraphRegexEvaluator
from core.evaluators.word_count import WordCountEvaluator


# --- word_count ---
def test_word_count_pass_under_max():
    e = WordCountEvaluator(max=10)
    score = e.run("one two three four five")
    assert score.value == 1.0


def test_word_count_pass_at_max():
    e = WordCountEvaluator(max=5)
    score = e.run("one two three four five")
    assert score.value == 1.0


def test_word_count_fail_over_max():
    e = WordCountEvaluator(max=3)
    score = e.run("one two three four five")
    assert score.value == 0.0
    assert "5" in score.reason
    assert "3" in score.reason


def test_word_count_pass_with_min():
    e = WordCountEvaluator(min=2, max=10)
    score = e.run("one two three")
    assert score.value == 1.0


def test_word_count_fail_under_min():
    e = WordCountEvaluator(min=5, max=10)
    score = e.run("only three words here")
    assert score.value == 0.0
    assert "min" in score.reason.lower() or "4" in score.reason


def test_word_count_handles_whitespace_and_newlines():
    e = WordCountEvaluator(max=4)
    score = e.run("  one\ttwo\n\nthree four  ")
    assert score.value == 1.0


def test_word_count_default_max_is_permissive():
    # No max set → never fails on length.
    e = WordCountEvaluator()
    score = e.run("a " * 10000)
    assert score.value == 1.0


def test_word_count_zero_words_fails_min():
    e = WordCountEvaluator(min=1)
    score = e.run("   ")
    assert score.value == 0.0


# --- last_paragraph_regex ---
def test_last_paragraph_regex_pass():
    e = LastParagraphRegexEvaluator(
        pattern=r"\b(reply|subscribe|join)\b", case_sensitive=False
    )
    text = (
        "Intro paragraph here.\n\n"
        "Middle paragraph with no CTA verbs.\n\n"
        "Reply with your take."
    )
    score = e.run(text)
    assert score.value == 1.0


def test_last_paragraph_regex_fail_when_cta_only_in_earlier_paragraph():
    e = LastParagraphRegexEvaluator(
        pattern=r"\b(reply|subscribe|join)\b", case_sensitive=False
    )
    text = (
        "Reply if you want — at the top.\n\n"
        "Middle.\n\n"
        "Closing line with no call to action."
    )
    score = e.run(text)
    assert score.value == 0.0
    assert "last paragraph" in score.reason.lower() or "final" in score.reason.lower()


def test_last_paragraph_regex_handles_single_paragraph():
    e = LastParagraphRegexEvaluator(pattern=r"subscribe")
    score = e.run("Please subscribe today.")
    assert score.value == 1.0


def test_last_paragraph_regex_handles_trailing_whitespace():
    e = LastParagraphRegexEvaluator(pattern=r"Reply")
    score = e.run("Intro.\n\nReply now.\n\n   \n")
    assert score.value == 1.0


def test_last_paragraph_regex_case_insensitive_optional():
    e = LastParagraphRegexEvaluator(pattern=r"reply", case_sensitive=False)
    score = e.run("Intro.\n\nREPLY now.")
    assert score.value == 1.0


def test_last_paragraph_regex_empty_response_fails():
    e = LastParagraphRegexEvaluator(pattern=r"reply")
    score = e.run("")
    assert score.value == 0.0


# --- registry wiring ---
@pytest.mark.parametrize("name", ["word_count", "last_paragraph_regex"])
def test_newsletter_evaluators_registered_in_registry(name):
    assert name in EVALUATOR_REGISTRY


@pytest.mark.parametrize("name", ["word_count", "last_paragraph_regex"])
def test_newsletter_evaluators_registered_as_builtin_factories(name):
    """Registration in BUILTIN_EVALUATOR_FACTORIES is what the gateway and
    the standalone CLI both consult — without it, the contract would
    silent-skip (T-0201).
    """
    assert name in BUILTIN_EVALUATOR_FACTORIES
    factory = BUILTIN_EVALUATOR_FACTORIES[name]
    instance = factory({"max": 5} if name == "word_count" else {"pattern": "x"})
    assert hasattr(instance, "run")


def test_legacy_underscore_run_alias_word_count():
    e = WordCountEvaluator(max=5)
    assert e._run == e.run


def test_legacy_underscore_run_alias_last_paragraph_regex():
    e = LastParagraphRegexEvaluator(pattern=r".")
    assert e._run == e.run
