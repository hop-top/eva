# tests/e2e/test_sentence_paragraph_count_evaluator.py
"""E2E tests: sentence_count / paragraph_count evaluator (T-0323, US-047).

One test case per acceptance bullet in docs/stories/US-047-sentence-paragraph-count-evaluator.md.
"""
from __future__ import annotations

from core.evaluators.sentence_paragraph_count import (
    SentenceParagraphCountEvaluator,
)
from core.models import Score


# AC1: sentence mode within [min, max] -> pass.
def test_sentence_count_within_bounds_passes():
    body = "Hello world. This is fine. And so is this."
    ev = SentenceParagraphCountEvaluator(mode="sentence", min=2, max=5)
    score = ev.run(body)
    assert isinstance(score, Score)
    assert score.value == 1.0


# AC2: sentence count out of bounds -> fail, naming count + bound.
def test_sentence_count_too_few_fails():
    body = "Just one sentence."
    ev = SentenceParagraphCountEvaluator(mode="sentence", min=3, max=10)
    score = ev.run(body)
    assert score.value == 0.0
    assert "1" in (score.reason or "")
    assert "min" in (score.reason or "")


# AC3: abbreviations don't split — "Dr. Smith said hi." = 1 sentence.
def test_abbreviations_do_not_split_sentences():
    body = "Dr. Smith said hi to Mr. Jones."
    ev = SentenceParagraphCountEvaluator(mode="sentence", min=1, max=1)
    score = ev.run(body)
    assert score.value == 1.0


# AC4: bullet items count as one sentence each.
def test_bullets_each_count_as_one_sentence():
    body = (
        "Intro line.\n"
        "- first bullet no period\n"
        "- second bullet.\n"
        "- third bullet!\n"
    )
    # Intro (1) + 3 bullets = 4 sentences.
    ev = SentenceParagraphCountEvaluator(mode="sentence", min=4, max=4)
    score = ev.run(body)
    assert score.value == 1.0


# AC5: paragraph mode within bounds -> pass.
def test_paragraph_count_within_bounds_passes():
    body = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    ev = SentenceParagraphCountEvaluator(mode="paragraph", min=1, max=5)
    score = ev.run(body)
    assert score.value == 1.0


# AC6: paragraph count out of bounds -> fail naming count.
def test_paragraph_count_too_many_fails():
    body = "A.\n\nB.\n\nC.\n\nD.\n\nE."
    ev = SentenceParagraphCountEvaluator(mode="paragraph", max=3)
    score = ev.run(body)
    assert score.value == 0.0
    assert "5" in (score.reason or "")


# AC7: contiguous blockquote group counts as one paragraph block.
def test_blockquote_group_counts_as_one_paragraph():
    body = (
        "Intro.\n\n"
        "> Quoted line one.\n"
        "> Quoted line two.\n"
        "> Quoted line three.\n\n"
        "Outro."
    )
    # 3 paragraphs: intro, blockquote block, outro.
    ev = SentenceParagraphCountEvaluator(mode="paragraph", min=3, max=3)
    score = ev.run(body)
    assert score.value == 1.0


# AC8: degenerate config (no min, no max) -> pass any non-empty.
def test_degenerate_config_passes():
    ev = SentenceParagraphCountEvaluator(mode="sentence")
    score = ev.run("Anything goes here.")
    assert score.value == 1.0
