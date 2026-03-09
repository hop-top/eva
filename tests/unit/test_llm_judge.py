# tests/unit/test_llm_judge.py
import pytest
from unittest.mock import AsyncMock
from core.evaluators.llm_judge import (
    parse_score,
    RelevanceEvaluator,
    HallucinationEvaluator,
    ToneEvaluator,
    TaskCompletionEvaluator,
    SafetyEvaluator,
)
from core.models import Score


# ---------------------------------------------------------------------------
# parse_score helper
# ---------------------------------------------------------------------------

def test_parse_score_basic():
    value, reason = parse_score("0.8\nLooks good")
    assert value == pytest.approx(0.8)
    assert reason == "Looks good"


def test_parse_score_no_reason():
    value, reason = parse_score("1.0")
    assert value == pytest.approx(1.0)
    assert reason == ""


def test_parse_score_clamps_above_one():
    value, _ = parse_score("1.5")
    assert value == pytest.approx(1.0)


def test_parse_score_clamps_below_zero():
    value, _ = parse_score("-0.3")
    assert value == pytest.approx(0.0)


def test_parse_score_fallback_on_garbage():
    value, reason = parse_score("not a number\nexplanation")
    assert value == pytest.approx(0.5)
    assert "not a number" in reason


def test_parse_score_fallback_on_empty():
    value, _ = parse_score("")
    assert value == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Shared mock factory
# ---------------------------------------------------------------------------

def make_mock_llm(reply: str) -> AsyncMock:
    mock = AsyncMock()
    mock.complete = AsyncMock(return_value=reply)
    return mock


# ---------------------------------------------------------------------------
# RelevanceEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_relevance_evaluator_passes_score():
    llm = make_mock_llm("0.9\nHighly relevant response.")
    ev = RelevanceEvaluator(llm_adapter=llm)
    score = await ev.evaluate(prompt="What is Python?", response="Python is a language.")
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.9)
    assert "Highly relevant" in score.reason


@pytest.mark.asyncio
async def test_relevance_evaluator_fallback():
    llm = make_mock_llm("oops")
    ev = RelevanceEvaluator(llm_adapter=llm)
    score = await ev.evaluate(prompt="q", response="r")
    assert score.value == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# HallucinationEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_hallucination_evaluator():
    llm = make_mock_llm("0.2\nContains several false facts.")
    ev = HallucinationEvaluator(llm_adapter=llm)
    score = await ev.evaluate(prompt="q", response="r")
    assert score.value == pytest.approx(0.2)
    assert score.metadata["evaluator_id"] == "hallucination"


# ---------------------------------------------------------------------------
# ToneEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tone_evaluator_default_professional():
    llm = make_mock_llm("0.7\nMostly professional tone.")
    ev = ToneEvaluator(llm_adapter=llm)
    assert ev.expected_tone == "professional"
    score = await ev.evaluate(prompt="q", response="r")
    assert score.value == pytest.approx(0.7)


@pytest.mark.asyncio
async def test_tone_evaluator_custom_tone():
    llm = make_mock_llm("0.5\nPartially casual.")
    ev = ToneEvaluator(llm_adapter=llm, expected_tone="casual")
    assert ev.expected_tone == "casual"
    # Judge prompt should mention expected tone
    await ev.evaluate(prompt="q", response="r")
    call_args = llm.complete.call_args
    assert "casual" in call_args[0][0][0]["content"]


# ---------------------------------------------------------------------------
# TaskCompletionEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_task_completion_evaluator():
    llm = make_mock_llm("1.0\nFully addressed.")
    ev = TaskCompletionEvaluator(llm_adapter=llm)
    score = await ev.evaluate(prompt="q", response="r")
    assert score.value == pytest.approx(1.0)
    assert score.metadata["evaluator_id"] == "task_completion"


# ---------------------------------------------------------------------------
# SafetyEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_safety_evaluator_safe():
    llm = make_mock_llm("1.0\nNo harmful content.")
    ev = SafetyEvaluator(llm_adapter=llm)
    score = await ev.evaluate(prompt="q", response="r")
    assert score.value == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_safety_evaluator_unsafe():
    llm = make_mock_llm("0.0\nHarmful content detected.")
    ev = SafetyEvaluator(llm_adapter=llm)
    score = await ev.evaluate(prompt="q", response="r")
    assert score.value == pytest.approx(0.0)
    assert score.metadata["evaluator_id"] == "safety"
