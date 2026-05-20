# tests/e2e/test_content_evaluators.py
"""E2E tests: content evaluators (bias, toxicity, summarization, alignment, goal accuracy)."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from core.dataset import EvaTestCase
from core.evaluators.llm_judge import (
    BiasEvaluator,
    GoalAccuracyEvaluator,
    PromptAlignmentEvaluator,
    SummarizationEvaluator,
    ToxicityEvaluator,
)
from core.models import Score


def make_mock_llm(reply: str) -> AsyncMock:
    mock = AsyncMock()
    completion = MagicMock()
    completion.content = reply
    mock.complete = AsyncMock(return_value=completion)
    return mock


# ---------------------------------------------------------------------------
# BiasEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bias_evaluator_unbiased():
    tc = EvaTestCase(id="tc-c01", input="Describe a good engineer.")
    llm = make_mock_llm("0.9\nNo bias detected in response.")
    ev = BiasEvaluator(llm_adapter=llm)
    score = await ev.evaluate(prompt=tc.input, response="A good engineer solves problems.")
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.9)
    assert score.metadata.get("evaluator_id") == "bias"


@pytest.mark.asyncio
async def test_bias_evaluator_biased():
    tc = EvaTestCase(id="tc-c02", input="Who makes the best leaders?")
    llm = make_mock_llm("0.1\nResponse shows strong gender bias.")
    ev = BiasEvaluator(llm_adapter=llm)
    score = await ev.evaluate(prompt=tc.input, response="Men are natural leaders.")
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# ToxicityEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_toxicity_evaluator():
    tc = EvaTestCase(id="tc-c03", input="Respond to user greeting.")
    llm = make_mock_llm("0.95\nCompletely non-toxic response.")
    ev = ToxicityEvaluator(llm_adapter=llm)
    score = await ev.evaluate(prompt=tc.input, response="Hello! How can I help you today?")
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.95)


# ---------------------------------------------------------------------------
# SummarizationEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_summarization_with_source():
    source = "Python is a high-level, interpreted language known for readability."
    captured_messages = []

    async def capturing_complete(messages):
        captured_messages.extend(messages)
        c = MagicMock()
        c.content = "0.88\nSummary captures key facts."
        return c

    mock_llm = MagicMock()
    mock_llm.complete = capturing_complete

    ev = SummarizationEvaluator(llm_adapter=mock_llm, source_text=source)
    score = await ev.evaluate(
        prompt="Summarize",
        response="Python is a readable, high-level language.",
    )

    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.88)
    combined = " ".join(str(m) for m in captured_messages)
    assert "Python" in combined


@pytest.mark.asyncio
async def test_summarization_without_source():
    tc = EvaTestCase(id="tc-c05", input="Summarize this document")
    llm = make_mock_llm("0.7\nDecent quality summary.")
    ev = SummarizationEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt=tc.input,
        response="The document covers AI evaluation frameworks.",
    )
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# PromptAlignmentEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_prompt_alignment():
    tc = EvaTestCase(id="tc-c06", input="Respond in exactly 3 bullet points.")
    llm = make_mock_llm("0.9\nAll instructions followed.")
    ev = PromptAlignmentEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt=tc.input,
        response="- Point 1\n- Point 2\n- Point 3",
    )
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# GoalAccuracyEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_goal_accuracy_from_constructor():
    llm = make_mock_llm("0.85\nOutput matches expected closely.")
    ev = GoalAccuracyEvaluator(llm_adapter=llm, expected_output="Paris")
    score = await ev.evaluate(
        prompt="What is the capital of France?",
        response="Paris",
    )
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.85)


@pytest.mark.asyncio
async def test_goal_accuracy_from_context():
    tc = EvaTestCase(
        id="tc-c08",
        input="What is 2+2?",
        expected_output="4",
    )
    llm = make_mock_llm("1.0\nPerfect match.")
    ev = GoalAccuracyEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt=tc.input,
        response="4",
        expected_output=tc.expected_output,
    )
    assert isinstance(score, Score)
    assert score.value == pytest.approx(1.0)
