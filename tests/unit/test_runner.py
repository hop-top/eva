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
