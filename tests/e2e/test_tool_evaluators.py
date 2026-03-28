# tests/e2e/test_tool_evaluators.py
"""E2E tests: tool-use evaluators wired to dataset loading."""
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, MagicMock

from core.dataset import EvaTestCase, load_dataset
from core.evaluators.llm_judge import (
    ArgumentCorrectnessEvaluator,
    GEvalEvaluator,
    PlanAdherenceEvaluator,
    PlanQualityEvaluator,
    StepEfficiencyEvaluator,
    ToolCorrectnessEvaluator,
    ToolUseEvaluator,
)
from core.models import Score


def make_mock_llm(reply: str) -> AsyncMock:
    mock = AsyncMock()
    completion = MagicMock()
    completion.content = reply
    mock.complete = AsyncMock(return_value=completion)
    return mock


# ---------------------------------------------------------------------------
# ToolCorrectnessEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tool_correctness_matching_tools():
    tc = EvaTestCase(id="tc-t01", input="Search for Python docs")
    llm = make_mock_llm("0.9\nCorrect tool used.")
    ev = ToolCorrectnessEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt=tc.input,
        response="Found Python docs.",
        tool_events=[{"tool_name": "search", "args": {"query": "Python docs"}}],
        expected_tools=["search"],
    )
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_tool_correctness_wrong_tools():
    tc = EvaTestCase(id="tc-t02", input="Search for Go docs")
    llm = make_mock_llm("0.2\nWrong tool used.")
    ev = ToolCorrectnessEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt=tc.input,
        response="Used calculator instead.",
        tool_events=[{"tool_name": "calculator", "args": {}}],
        expected_tools=["search"],
    )
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# ArgumentCorrectnessEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_argument_correctness():
    tc = EvaTestCase(id="tc-t03", input="Find capital of France")
    llm = make_mock_llm("0.85\nArgs match expected.")
    ev = ArgumentCorrectnessEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt=tc.input,
        response="The capital is Paris.",
        tool_events=[{"tool_name": "lookup", "args": {"country": "France"}}],
        expected_args={"country": "France"},
    )
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.85)


# ---------------------------------------------------------------------------
# ToolUseEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tool_use_evaluator():
    tc = EvaTestCase(id="tc-t04", input="Summarize this article")
    llm = make_mock_llm("0.7\nReasonable tool usage.")
    ev = ToolUseEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt=tc.input,
        response="Summary produced.",
        tool_events=[{"tool_name": "summarize", "args": {"text": "..."}}],
    )
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# StepEfficiencyEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_step_efficiency():
    tc = EvaTestCase(
        id="tc-t05",
        input="Book a flight",
        planned_steps=["search flights", "select flight"],
    )
    llm = make_mock_llm("0.6\nUsed more steps than planned.")
    ev = StepEfficiencyEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt=tc.input,
        response="Flight booked.",
        planned_steps=tc.planned_steps,
        tool_events=[
            {"tool_name": "search_flights", "args": {}},
            {"tool_name": "filter_results", "args": {}},
            {"tool_name": "book_flight", "args": {}},
        ],
    )
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.6)


# ---------------------------------------------------------------------------
# PlanAdherenceEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_plan_adherence():
    tc = EvaTestCase(
        id="tc-t06",
        input="Deploy service",
        planned_steps=["build", "test", "deploy"],
    )
    llm = make_mock_llm("0.8\nMost steps followed in order.")
    ev = PlanAdherenceEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt=tc.input,
        response="Service deployed after build and test.",
        planned_steps=tc.planned_steps,
    )
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# PlanQualityEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_plan_quality():
    tc = EvaTestCase(id="tc-t07", input="Plan a database migration")
    llm = make_mock_llm("0.75\nPlan is feasible and complete.")
    ev = PlanQualityEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt=tc.input,
        response="1. Backup 2. Migrate schema 3. Migrate data 4. Validate",
    )
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# GEvalEvaluator — custom criteria prompt inspection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_geval_custom_criteria():
    captured_messages = []

    async def capturing_complete(messages):
        captured_messages.extend(messages)
        c = MagicMock()
        c.content = "0.8\nCites a source."
        return c

    mock_llm = MagicMock()
    mock_llm.complete = capturing_complete

    ev = GEvalEvaluator(llm_adapter=mock_llm, criteria="Must cite a source")
    score = await ev.evaluate(
        prompt="Explain gravity",
        response="According to Newton (1687), gravity is...",
    )

    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.8)
    assert len(captured_messages) > 0
    combined = " ".join(str(m) for m in captured_messages)
    assert "cite a source" in combined


# ---------------------------------------------------------------------------
# Dataset loading — planned_steps field
# ---------------------------------------------------------------------------

def test_dataset_loads_planned_steps(tmp_path: Path):
    yaml_content = """
name: tool-test
target: http://localhost:9999
tests:
  - id: tc-ps01
    input: Execute pipeline
    planned_steps:
      - fetch data
      - process data
      - store results
"""
    ds_file = tmp_path / "tool_dataset.yaml"
    ds_file.write_text(yaml_content)

    dataset = load_dataset(ds_file)
    assert len(dataset.tests) == 1
    tc = dataset.tests[0]
    assert tc.planned_steps == ["fetch data", "process data", "store results"]
