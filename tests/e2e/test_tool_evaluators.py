# tests/e2e/test_tool_evaluators.py
"""E2E tests: tool-use evaluators wired to dataset loading.

One test case per US-032 acceptance-criterion bullet:
  AC1 planned_steps in dataset YAML            -> test_dataset_loads_planned_steps
  AC2 tool_correctness                         -> test_tool_correctness_*
  AC3 argument_correctness                     -> test_argument_correctness
  AC4 tool_use (holistic)                      -> test_tool_use_evaluator
  AC5 step_efficiency                          -> test_step_efficiency
  AC6 plan_adherence                           -> test_plan_adherence
  AC7 plan_quality                             -> test_plan_quality
  AC8 geval custom criteria                    -> test_geval_custom_criteria
  AC9 EventSink-driven tool events in context  -> test_tool_events_flow_via_event_sink_*
"""
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, MagicMock

from core.dataset import Dataset, EvaTestCase, load_dataset
# Import via the US-032 dedicated module locations to exercise the new
# `core/evaluators/<name>.py` modules added by T-0291.
from core.evaluators.argument_correctness import ArgumentCorrectnessEvaluator
from core.evaluators.geval import GEvalEvaluator
from core.evaluators.plan_adherence import PlanAdherenceEvaluator
from core.evaluators.plan_quality import PlanQualityEvaluator
from core.evaluators.step_efficiency import StepEfficiencyEvaluator
from core.evaluators.tool_correctness import ToolCorrectnessEvaluator
from core.evaluators.tool_use import ToolUseEvaluator
from core.events import EventSink
from core.models import Score
from core.plugins import EvaPlugin, EvaSpec, make_manager
from core.runner import Runner


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


# ---------------------------------------------------------------------------
# AC9 — tool events flow into the evaluator context via EventSink
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tool_events_flow_via_event_sink_to_run_eval_context():
    """Tool events emitted into the per-invocation EventSink during the
    run must appear in the ``context['tool_events']`` payload that the
    runner hands to plugin hooks.

    Production pattern (per commit afd9c88): each invocation gets its
    own EventSink exposed via ``run_ctx['event_sink']``. Plugins emit
    into it through the ``before_eval`` hook; the runner snapshots the
    sink's events into ``context['tool_events']`` for evaluators.
    """
    captured: list[dict] = []

    class CapturePlugin(EvaPlugin):
        @EvaSpec.hook_impl
        def before_eval(self, test_id: str, context: dict) -> None:
            # Emit tool events into the per-invocation sink the runner
            # installed for this test. This is the production seam:
            # production agents do the same from their tool-call adapter.
            sink = context["event_sink"]
            sink.emit_tool_call("search", {"query": "Python docs"}, result="ok")
            sink.emit_tool_call("fetch", {"url": "https://example.com"}, result="200")

        @EvaSpec.hook_impl
        def run_eval(self, response: str, context: dict) -> Score:
            captured.append(context)
            return Score(value=1.0)

    pm = make_manager()
    pm.register(CapturePlugin())

    async def fake_agent(prompt: str, target: str) -> str:
        return "done"

    ds = Dataset(
        name="ac9",
        target="http://unused",
        evaluators=[{"name": "capture", "mode": "binary"}],
        tests=[EvaTestCase(id="ac9-1", input="hi", planned_steps=["s1", "s2"])],
    )

    runner = Runner(pm=pm, call_agent=fake_agent)
    await runner.execute(ds)

    assert len(captured) == 1
    ctx = captured[0]
    assert "tool_events" in ctx, "runner must inject tool_events into context"
    tool_events = ctx["tool_events"]
    assert isinstance(tool_events, list) and len(tool_events) == 2
    # planned_steps should also be threaded into ctx so tool-use evaluators
    # like step_efficiency / plan_adherence can read it.
    assert ctx.get("planned_steps") == ["s1", "s2"]


@pytest.mark.asyncio
async def test_tool_correctness_consumes_event_sink_context():
    """End-to-end: the evaluator reads tool_events emitted via EventSink."""
    sink = EventSink()
    sink.emit_tool_call("search", {"query": "q"}, result="ok")

    llm = make_mock_llm("1.0\nUsed expected tool.")
    ev = ToolCorrectnessEvaluator(llm_adapter=llm)

    tool_events = [
        {"tool_name": e.tool_name, "args": e.args} for e in sink.events
    ]
    score = await ev.evaluate(
        prompt="Look it up",
        response="found it",
        tool_events=tool_events,
        expected_tools=["search"],
    )
    assert isinstance(score, Score)
    assert score.value == pytest.approx(1.0)
