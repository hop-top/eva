# tests/unit/test_runner.py
import pytest
from unittest.mock import AsyncMock, patch
from core.runner import Runner
from core.dataset import Dataset, EvaTestCase
from core.models import Score
from core.plugins import EvaPlugin, EvaSpec


class AlwaysPassPlugin(EvaPlugin):
    @EvaSpec.hook_impl
    def run_eval(self, response: str, context: dict) -> Score:
        return Score(value=1.0)


class AlwaysFailPlugin(EvaPlugin):
    @EvaSpec.hook_impl
    def run_eval(self, response: str, context: dict) -> Score:
        return Score(value=0.0, reason="always fails")


DATASET = Dataset(
    name="test_suite",
    target="http://fake-agent/chat",
    evaluators=[{"name": "always_pass", "mode": "binary"}],
    tests=[
        EvaTestCase(id="t1", input="hello"),
        EvaTestCase(id="t2", input="world"),
    ],
)


@pytest.mark.asyncio
async def test_runner_all_pass():
    from core.plugins import make_manager
    pm = make_manager()
    pm.register(AlwaysPassPlugin())

    async def fake_call(input: str, target: str) -> str:
        return "ok response"

    runner = Runner(pm=pm, call_agent=fake_call)
    run = await runner.execute(DATASET)
    assert run.passed is True
    assert len(run.results) == 2


@pytest.mark.asyncio
async def test_runner_one_fail():
    from core.plugins import make_manager
    pm = make_manager()
    pm.register(AlwaysFailPlugin())

    async def fake_call(input: str, target: str) -> str:
        return "bad response"

    runner = Runner(pm=pm, call_agent=fake_call)
    run = await runner.execute(DATASET)
    assert run.passed is False


@pytest.mark.asyncio
async def test_runner_records_duration():
    from core.plugins import make_manager
    pm = make_manager()
    pm.register(AlwaysPassPlugin())

    async def fake_call(input: str, target: str) -> str:
        return "ok"

    runner = Runner(pm=pm, call_agent=fake_call)
    run = await runner.execute(DATASET)
    assert run.duration_ms >= 0
    assert all(r.duration_ms >= 0 for r in run.results)


# ---------------------------------------------------------------------------
# T-0027: mode/min_score wiring from evaluator config
# ---------------------------------------------------------------------------

DATASET_THRESHOLD = Dataset(
    name="threshold_suite",
    target="http://fake-agent/chat",
    evaluators=[{"name": "my_eval", "mode": "threshold", "min_score": 0.6}],
    tests=[EvaTestCase(id="t1", input="hello")],
)


@pytest.mark.asyncio
async def test_runner_reads_mode_from_evaluator_config():
    from core.plugins import make_manager
    pm = make_manager()
    pm.register(AlwaysPassPlugin())

    async def fake_call(input: str, target: str) -> str:
        return "ok"

    runner = Runner(pm=pm, call_agent=fake_call)
    run = await runner.execute(DATASET_THRESHOLD)
    assert run.results[0].mode == "threshold"
    assert run.results[0].min_score == pytest.approx(0.6)
    assert run.results[0].evaluator == "my_eval"


@pytest.mark.asyncio
async def test_runner_reads_min_score_from_evaluator_config():
    """Score 1.0 with threshold 0.6 → passed."""
    from core.plugins import make_manager
    pm = make_manager()
    pm.register(AlwaysPassPlugin())

    async def fake_call(input: str, target: str) -> str:
        return "ok"

    runner = Runner(pm=pm, call_agent=fake_call)
    run = await runner.execute(DATASET_THRESHOLD)
    assert run.results[0].passed is True


@pytest.mark.asyncio
async def test_runner_fallback_min_score_from_constructor():
    """No min_score in config → use constructor default."""
    from core.plugins import make_manager
    pm = make_manager()
    pm.register(AlwaysPassPlugin())

    dataset = Dataset(
        name="no_min_score",
        target="http://fake",
        evaluators=[{"name": "x", "mode": "threshold"}],
        tests=[EvaTestCase(id="t1", input="hi")],
    )

    async def fake_call(input: str, target: str) -> str:
        return "ok"

    runner = Runner(pm=pm, call_agent=fake_call, min_score=0.7)
    run = await runner.execute(dataset)
    assert run.results[0].min_score == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# T-0028: concurrency modes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_runner_sequential_mode():
    from core.plugins import make_manager
    pm = make_manager()
    pm.register(AlwaysPassPlugin())

    order: list[str] = []

    async def fake_call(input: str, target: str) -> str:
        order.append(input)
        return "ok"

    dataset = Dataset(
        name="seq",
        target="http://fake",
        evaluators=[{"name": "x", "mode": "binary"}],
        tests=[EvaTestCase(id=f"t{i}", input=f"in{i}") for i in range(4)],
    )
    runner = Runner(pm=pm, call_agent=fake_call, concurrency="sequential")
    run = await runner.execute(dataset)
    assert run.passed is True
    assert len(run.results) == 4


@pytest.mark.asyncio
async def test_runner_semaphore_mode():
    from core.plugins import make_manager
    pm = make_manager()
    pm.register(AlwaysPassPlugin())

    async def fake_call(input: str, target: str) -> str:
        return "ok"

    dataset = Dataset(
        name="sem",
        target="http://fake",
        evaluators=[{"name": "x", "mode": "binary"}],
        tests=[EvaTestCase(id=f"t{i}", input=f"in{i}") for i in range(6)],
    )
    runner = Runner(pm=pm, call_agent=fake_call, concurrency="semaphore", max_workers=3)
    run = await runner.execute(dataset)
    assert run.passed is True
    assert len(run.results) == 6


@pytest.mark.asyncio
async def test_runner_parallel_mode():
    from core.plugins import make_manager
    pm = make_manager()
    pm.register(AlwaysPassPlugin())

    async def fake_call(input: str, target: str) -> str:
        return "ok"

    dataset = Dataset(
        name="par",
        target="http://fake",
        evaluators=[{"name": "x", "mode": "binary"}],
        tests=[EvaTestCase(id=f"t{i}", input=f"in{i}") for i in range(4)],
    )
    runner = Runner(pm=pm, call_agent=fake_call, concurrency="parallel", max_workers=2)
    run = await runner.execute(dataset)
    assert run.passed is True


@pytest.mark.asyncio
async def test_runner_max_workers_1_is_sequential():
    from core.plugins import make_manager
    pm = make_manager()
    pm.register(AlwaysPassPlugin())

    async def fake_call(input: str, target: str) -> str:
        return "ok"

    dataset = Dataset(
        name="w1",
        target="http://fake",
        evaluators=[{"name": "x", "mode": "binary"}],
        tests=[EvaTestCase(id=f"t{i}", input=f"in{i}") for i in range(3)],
    )
    runner = Runner(pm=pm, call_agent=fake_call, concurrency="semaphore", max_workers=1)
    run = await runner.execute(dataset)
    assert run.passed is True


@pytest.mark.asyncio
async def test_runner_legacy_int_concurrency():
    """Old callers pass concurrency as int — must still work."""
    from core.plugins import make_manager
    pm = make_manager()
    pm.register(AlwaysPassPlugin())

    async def fake_call(input: str, target: str) -> str:
        return "ok"

    runner = Runner(pm=pm, call_agent=fake_call, concurrency=2)
    run = await runner.execute(DATASET)
    assert run.passed is True


# ---------------------------------------------------------------------------
# T-0027: otel_adapter accepted without error
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_runner_accepts_custom_otel_adapter():
    from core.plugins import make_manager
    pm = make_manager()
    pm.register(AlwaysPassPlugin())

    class FakeSpan:
        def __enter__(self): return self
        def __exit__(self, *_): pass

    class FakeOtel:
        def start_span(self, name, **attrs): return FakeSpan()

    async def fake_call(input: str, target: str) -> str:
        return "ok"

    runner = Runner(pm=pm, call_agent=fake_call, otel_adapter=FakeOtel())
    run = await runner.execute(DATASET)
    assert run.passed is True


# ---------------------------------------------------------------------------
# T-0168: tool_events passed into run_eval context
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_runner_passes_tool_events_to_evaluator_context():
    """tool_events key must appear in context passed to run_eval."""
    from core.plugins import make_manager
    from core.events import EventSink

    captured_contexts: list[dict] = []

    class ContextCapturingPlugin(EvaPlugin):
        @EvaSpec.hook_impl
        def run_eval(self, response: str, context: dict) -> Score:
            captured_contexts.append(context)
            return Score(value=1.0)

    pm = make_manager()
    pm.register(ContextCapturingPlugin())

    sink = EventSink()
    sink.emit_tool_call("search", {"query": "test"}, result="some result")

    async def fake_call(input: str, target: str) -> str:
        return "ok"

    dataset = Dataset(
        name="tool_events_test",
        target="http://fake",
        evaluators=[{"name": "x", "mode": "binary"}],
        tests=[EvaTestCase(id="t1", input="hello")],
    )

    runner = Runner(pm=pm, call_agent=fake_call, event_sink=sink)
    await runner.execute(dataset)

    assert len(captured_contexts) == 1
    assert "tool_events" in captured_contexts[0]
    assert isinstance(captured_contexts[0]["tool_events"], list)
