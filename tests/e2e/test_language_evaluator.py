# tests/e2e/test_language_evaluator.py
"""E2E: language evaluator (US-039, T-0298).

One test per acceptance bullet on docs/stories/US-039-language-evaluator.md.
"""
from __future__ import annotations

import pytest

from core.evaluators.language import LanguageEvaluator
from core.models import Score


# ---------------------------------------------------------------------------
# Latin-script passes
# ---------------------------------------------------------------------------

def test_english_pass():
    ev = LanguageEvaluator(expected="en")
    score = ev.run("The quick brown fox jumps over the lazy dog.")
    assert isinstance(score, Score)
    assert score.value == 1.0


def test_french_pass():
    ev = LanguageEvaluator(expected="fr")
    score = ev.run("Le chat est sur la table et le chien est dans le jardin.")
    assert score.value == 1.0


def test_spanish_pass():
    ev = LanguageEvaluator(expected="es")
    score = ev.run("El gato está sobre la mesa y el perro está en el jardín.")
    assert score.value == 1.0


# ---------------------------------------------------------------------------
# Wrong-language failure
# ---------------------------------------------------------------------------

def test_wrong_language_fail_with_diagnostic():
    """English response when French is expected → 0.0 with reason naming both."""
    ev = LanguageEvaluator(expected="fr")
    score = ev.run("The cat is on the table and the dog is in the garden.")
    assert score.value == 0.0
    assert score.reason is not None
    assert "fr" in score.reason
    assert "en" in score.reason


# ---------------------------------------------------------------------------
# Non-Latin script
# ---------------------------------------------------------------------------

def test_japanese_pass_via_script_detection():
    ev = LanguageEvaluator(expected="ja")
    score = ev.run("これは日本語のテストです。テキストを評価します。")
    assert score.value == 1.0


# ---------------------------------------------------------------------------
# Ambiguous / mixed
# ---------------------------------------------------------------------------

def test_mixed_language_input_scores_zero():
    """50/50 mixed input should not be confidently classified — score 0.0."""
    ev = LanguageEvaluator(expected="fr")
    # Equal token counts French + Spanish stoplist hits.
    score = ev.run("le la les de et el la los de y")
    assert score.value == 0.0


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------

def test_empty_response_scores_zero_no_crash():
    ev = LanguageEvaluator(expected="en")
    score = ev.run("")
    assert score.value == 0.0


def test_whitespace_only_response_scores_zero_no_crash():
    ev = LanguageEvaluator(expected="en")
    score = ev.run("   \n   ")
    assert score.value == 0.0


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------

def test_unsupported_expected_language_raises():
    with pytest.raises(ValueError):
        LanguageEvaluator(expected="klingon")
