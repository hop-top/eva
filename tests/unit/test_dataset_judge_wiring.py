# tests/unit/test_dataset_judge_wiring.py
"""Dataset-mode builtin + judge evaluator wiring.

Covers:
  * builtin (programmatic) evaluators scoring in dataset mode
  * judge evaluators awaited through a stub async adapter
  * judge refs skipping with a reason when no adapter is configured
  * the score/config alignment fix (regression test — see
    test_alignment_builtin_config_not_stolen_by_plugin)
  * build_llm_adapter resolution order
"""
import pytest

from core.config import EvaConfig, JudgeConfig
from core.dataset import Dataset, EvaTestCase
from core.llm import LLMCompletion, build_llm_adapter
from core.models import Score
from core.plugins import EvaPlugin, EvaSpec, make_manager
from core.runner import Runner


async def fake_call(input: str, target: str) -> str:
    return "response mentioning waldo"


class StubJudgeAdapter:
    """Async adapter double: returns a canned judge verdict."""

    def __init__(self, content: str = "0.8\nlooks good"):
        self.content = content
        self.calls: list[list[dict]] = []

    async def complete(self, messages, **kwargs):
        self.calls.append(messages)
        return LLMCompletion(
            content=self.content,
            provider="stub",
            model="stub-model",
            usage={},
            raw_response=None,
        )


class NamedPlugin(EvaPlugin):
    """Plugin that self-identifies via Score.metadata.evaluator_id."""

    @EvaSpec.hook_impl
    def run_eval(self, response: str, context: dict) -> Score:
        return Score(
            value=0.25,
            reason="plugin verdict",
            metadata={"evaluator_id": "my_plugin"},
        )


@pytest.mark.asyncio
async def test_builtin_contains_scores_in_dataset_mode():
    ds = Dataset(
        name="s",
        target="http://fake/agent",
        evaluators=[{"name": "contains", "substring": "waldo", "mode": "binary"}],
        tests=[EvaTestCase(id="t1", input="find waldo")],
    )
    runner = Runner(pm=make_manager(), call_agent=fake_call)
    run = await runner.execute(ds)
    assert len(run.results) == 1
    r = run.results[0]
    assert r.evaluator == "contains"
    assert r.score.value == 1.0
    assert r.passed is True
    assert run.skipped == []


@pytest.mark.asyncio
async def test_judge_evaluator_awaited_with_adapter():
    adapter = StubJudgeAdapter("0.8\nsolid work")
    ds = Dataset(
        name="s",
        target="http://fake/agent",
        evaluators=[{"name": "task_completion", "mode": "threshold", "min_score": 0.5}],
        tests=[EvaTestCase(id="t1", input="do the thing")],
    )
    runner = Runner(pm=make_manager(), call_agent=fake_call, llm_adapter=adapter)
    run = await runner.execute(ds)
    assert len(run.results) == 1
    r = run.results[0]
    assert r.evaluator == "task_completion"
    assert r.score.value == 0.8
    assert r.passed is True
    assert len(adapter.calls) == 1  # judge actually invoked


@pytest.mark.asyncio
async def test_judge_ref_skips_with_reason_when_unconfigured():
    ds = Dataset(
        name="s",
        target="http://fake/agent",
        evaluators=[
            {"name": "task_completion", "mode": "binary"},
            {"name": "contains", "substring": "waldo", "mode": "binary"},
        ],
        tests=[EvaTestCase(id="t1", input="hi")],
    )
    runner = Runner(pm=make_manager(), call_agent=fake_call, llm_adapter=None)
    run = await runner.execute(ds)
    # judge skipped, programmatic still ran; run did not blow up
    assert len(run.results) == 1
    assert run.results[0].evaluator == "contains"
    assert len(run.skipped) == 1
    assert run.skipped[0].startswith("task_completion:")
    assert "llm_adapter" in run.skipped[0]


@pytest.mark.asyncio
async def test_alignment_builtin_config_not_stolen_by_plugin():
    """Regression: plugin scores must never be positionally mislabeled with
    builtin evaluator configs (the old zip-by-index bug), and builtin refs
    must actually run instead of silently vanishing."""
    pm = make_manager()
    pm.register(NamedPlugin())
    ds = Dataset(
        name="s",
        target="http://fake/agent",
        evaluators=[
            # Old code: the single plugin score landed on index 0 and was
            # labeled "contains" (mode binary, contains' config) while the
            # contains evaluator itself never executed.
            {"name": "contains", "substring": "waldo", "mode": "binary"},
            {"name": "my_plugin", "mode": "threshold", "min_score": 0.2},
        ],
        tests=[EvaTestCase(id="t1", input="q")],
    )
    runner = Runner(pm=pm, call_agent=fake_call)
    run = await runner.execute(ds)
    by_name = {r.evaluator: r for r in run.results}
    assert set(by_name) == {"contains", "my_plugin"}
    assert by_name["contains"].score.value == 1.0  # builtin genuinely ran
    assert by_name["my_plugin"].score.value == 0.25
    assert by_name["my_plugin"].mode == "threshold"  # its own config, not contains'
    assert by_name["my_plugin"].passed is True  # 0.25 >= 0.2


@pytest.mark.asyncio
async def test_plugin_only_dataset_unchanged():
    """Backwards compat: plugin-only configs still pair positionally."""
    class AnonPlugin(EvaPlugin):
        @EvaSpec.hook_impl
        def run_eval(self, response: str, context: dict) -> Score:
            return Score(value=1.0)

    pm = make_manager()
    pm.register(AnonPlugin())
    ds = Dataset(
        name="s",
        target="http://fake/agent",
        evaluators=[{"name": "always_pass", "mode": "binary"}],
        tests=[EvaTestCase(id="t1", input="q")],
    )
    run = await Runner(pm=pm, call_agent=fake_call).execute(ds)
    assert len(run.results) == 1
    assert run.results[0].evaluator == "always_pass"
    assert run.results[0].passed is True


def test_build_llm_adapter_resolution(monkeypatch):
    monkeypatch.delenv("EVA_JUDGE_MODEL", raising=False)
    assert build_llm_adapter(EvaConfig()) is None
    assert build_llm_adapter(None) is None

    cfg = EvaConfig(judge=JudgeConfig(model="gpt-4o-mini", params={"temperature": 0}))
    adapter = build_llm_adapter(cfg)
    assert adapter is not None
    assert adapter.model == "gpt-4o-mini"
    assert adapter.kwargs == {"temperature": 0}

    monkeypatch.setenv("EVA_JUDGE_MODEL", "claude-sonnet-5")
    adapter = build_llm_adapter(cfg)
    assert adapter.model == "claude-sonnet-5"  # env wins over config
