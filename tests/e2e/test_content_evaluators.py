# tests/e2e/test_content_evaluators.py
"""E2E tests: content-quality evaluators (US-034).

One ``test_us034_ac*`` case per acceptance bullet in
``docs/stories/US-034-content-quality-evaluation.md``:

  AC1: ``bias`` — gender, racial, political; independent of the safety evaluator.
  AC2: ``toxicity`` — dedicated toxicity scoring, independent of other safety concerns.
  AC3: ``summarization`` — faithfulness against an optional source text.
  AC4: ``prompt_alignment`` — rates how well the response follows all instructions.
  AC5: ``goal_accuracy`` — measures whether the response matches the expected output.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.dataset import EvaTestCase
from core.evaluators.content_quality import (
    ContentBiasEvaluator,
    ContentGoalAccuracyEvaluator,
    ContentPromptAlignmentEvaluator,
    ContentSummarizationEvaluator,
    ContentToxicityEvaluator,
)
from core.evaluators.llm_judge import SafetyEvaluator
from core.models import Score


def make_mock_llm(reply: str) -> AsyncMock:
    mock = AsyncMock()
    completion = MagicMock()
    completion.content = reply
    mock.complete = AsyncMock(return_value=completion)
    return mock


def make_capturing_llm(reply: str) -> tuple[MagicMock, list]:
    captured: list = []

    async def capturing_complete(messages):
        captured.append(messages)
        completion = MagicMock()
        completion.content = reply
        return completion

    mock = MagicMock()
    mock.complete = capturing_complete
    return mock, captured


# ---------------------------------------------------------------------------
# AC1 — bias: independent of safety evaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_us034_ac1_bias_independent_of_safety():
    """ContentBiasEvaluator must:
       1. Score gender/racial/political bias as a standalone signal.
       2. Use a distinct prompt from SafetyEvaluator (not reuse safety's wording).
    """
    bias_llm, bias_captured = make_capturing_llm("0.1\nGender bias detected.")
    safety_llm, safety_captured = make_capturing_llm("0.5\nGenerally safe.")

    tc = EvaTestCase(id="tc-c01", input="Who makes the best engineers?")
    response = "Men are naturally better engineers than women."

    bias_score = await ContentBiasEvaluator(llm_adapter=bias_llm).evaluate(
        prompt=tc.input, response=response
    )
    safety_score = await SafetyEvaluator(llm_adapter=safety_llm).evaluate(
        prompt=tc.input, response=response
    )

    assert isinstance(bias_score, Score)
    assert bias_score.value == pytest.approx(0.1)
    assert bias_score.metadata["evaluator_id"] == "bias"

    # Independence: bias prompt must NOT be the safety prompt verbatim.
    bias_judge = " ".join(str(m) for m in bias_captured[0])
    safety_judge = " ".join(str(m) for m in safety_captured[0])
    assert bias_judge != safety_judge
    # Bias-specific dimensions surface in the bias prompt.
    assert "gender" in bias_judge.lower()
    assert "racial" in bias_judge.lower()
    assert "political" in bias_judge.lower()


# ---------------------------------------------------------------------------
# AC2 — toxicity: dedicated, separate from other safety concerns
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_us034_ac2_toxicity_independent_of_safety():
    tox_llm, tox_captured = make_capturing_llm("0.95\nCompletely non-toxic response.")
    safety_llm, safety_captured = make_capturing_llm("0.9\nSafe enough.")

    tc = EvaTestCase(id="tc-c03", input="Respond to user greeting.")
    response = "Hello! How can I help you today?"

    tox_score = await ContentToxicityEvaluator(llm_adapter=tox_llm).evaluate(
        prompt=tc.input, response=response
    )
    await SafetyEvaluator(llm_adapter=safety_llm).evaluate(
        prompt=tc.input, response=response
    )

    assert tox_score.value == pytest.approx(0.95)
    assert tox_score.metadata["evaluator_id"] == "toxicity"

    tox_judge = " ".join(str(m) for m in tox_captured[0])
    safety_judge = " ".join(str(m) for m in safety_captured[0])
    assert tox_judge != safety_judge
    # Toxicity-specific framing surfaces.
    assert "toxic" in tox_judge.lower()
    # Other safety concerns should be explicitly excluded from the toxicity prompt.
    assert "toxicity only" in tox_judge.lower()


# ---------------------------------------------------------------------------
# AC3 — summarization faithfulness against source text
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_us034_ac3_summarization_with_source():
    source = "Python is a high-level, interpreted language known for readability."
    llm, captured = make_capturing_llm("0.88\nSummary captures key facts.")

    ev = ContentSummarizationEvaluator(llm_adapter=llm, source_text=source)
    score = await ev.evaluate(
        prompt="Summarize",
        response="Python is a readable, high-level language.",
    )

    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.88)
    assert score.metadata["evaluator_id"] == "summarization"
    assert score.metadata["had_source_text"] is True

    # The judge must have actually seen the source.
    judge_text = " ".join(str(m) for m in captured[0])
    assert "high-level, interpreted language" in judge_text

    # Also covered: no-source fallback path.
    no_src_llm = make_mock_llm("0.7\nDecent quality summary.")
    no_src_ev = ContentSummarizationEvaluator(llm_adapter=no_src_llm)
    fallback_score = await no_src_ev.evaluate(
        prompt="Summarize this document",
        response="The document covers AI evaluation frameworks.",
    )
    assert fallback_score.value == pytest.approx(0.7)
    assert fallback_score.metadata["had_source_text"] is False


# ---------------------------------------------------------------------------
# AC4 — prompt_alignment: follows all instructions in the prompt
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_us034_ac4_prompt_alignment_follows_instructions():
    tc = EvaTestCase(
        id="tc-c06",
        input="Respond in exactly 3 bullet points and use the word 'simple' once.",
    )
    llm, captured = make_capturing_llm("0.9\nAll instructions followed.")
    ev = ContentPromptAlignmentEvaluator(llm_adapter=llm)

    score = await ev.evaluate(
        prompt=tc.input,
        response="- Simple point 1\n- Point 2\n- Point 3",
    )
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.9)
    assert score.metadata["evaluator_id"] == "prompt_alignment"

    judge_text = " ".join(str(m) for m in captured[0])
    # Prompt-alignment judge must explicitly reason about every instruction.
    assert "instruction" in judge_text.lower()


# ---------------------------------------------------------------------------
# AC5 — goal_accuracy: matches the expected output / goal
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_us034_ac5_goal_accuracy_matches_expected():
    # 1. expected_output passed via constructor
    llm_a = make_mock_llm("0.85\nOutput matches expected closely.")
    ev_a = ContentGoalAccuracyEvaluator(llm_adapter=llm_a, expected_output="Paris")
    score_a = await ev_a.evaluate(prompt="What is the capital of France?", response="Paris")
    assert score_a.value == pytest.approx(0.85)
    assert score_a.metadata["evaluator_id"] == "goal_accuracy"
    assert score_a.metadata["had_expected_output"] is True

    # 2. expected_output passed via context (e.g. from EvaTestCase)
    tc = EvaTestCase(id="tc-c08", input="What is 2+2?", expected_output="4")
    llm_b, captured = make_capturing_llm("1.0\nPerfect match.")
    ev_b = ContentGoalAccuracyEvaluator(llm_adapter=llm_b)
    score_b = await ev_b.evaluate(
        prompt=tc.input, response="4", expected_output=tc.expected_output
    )
    assert score_b.value == pytest.approx(1.0)
    assert score_b.metadata["had_expected_output"] is True
    # Judge prompt must include the expected output for comparison.
    judge_text = " ".join(str(m) for m in captured[0])
    assert "Expected output: 4" in judge_text
