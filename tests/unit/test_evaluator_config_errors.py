"""Invalid evaluator config fails a dataset run before any target call.

"Not applicable to this case" (a ``None`` score) and "judge needs an adapter"
(a skip) stay distinct from "this evaluator's config is wrong".
"""
from __future__ import annotations

import pytest

from core.dataset import Dataset
from core.evaluators.builtin import BUILTIN_EVALUATOR_FACTORIES
from core.evaluators.errors import EvaluatorConfigError, JudgeAdapterRequired
from core.evaluators.key_facts import KeyFactsConfigError
from core.plugins import make_manager
from core.runner import Runner

# name -> (bad config, text the error must carry: the key or value at fault)
BAD_CONFIGS = {
    "refusal": ({"mode": "sideways"}, "sideways"),
    "mood": ({"expected": "grumpy"}, "grumpy"),
    "language": ({"expected": "klingon"}, "klingon"),
    "equals": ({"expected": 1}, "field"),
    "status_code": ({}, "expected"),
    "exit_code": ({"expected": 0, "expected_in": [0]}, "mutually exclusive"),
    "json_path": ({"path": "$.a", "comparator": "approx"}, "approx"),
    "sentence_paragraph_count": ({"mode": "word"}, "word"),
    "code_test_passes": ({"timeout": None}, "timeout"),
    "code_tests": ({"language": "cobol"}, "cobol"),
    "ifeval_check": ({"pass_on": "sloppy"}, "sloppy"),
    "key_facts": ({"threshold": 5}, "threshold"),
    "regex": ({"pattern": "("}, "'('"),
    "last_paragraph_regex": ({"pattern": "(["}, "(["),
    "citation": ({"allowed_sources": 5}, "allowed_sources"),
    "prose_assertion": ({"assertion_mode": "wishful"}, "wishful"),
}


def _ds(evaluators):
    return Dataset(
        name="d",
        target="http://x",
        evaluators=evaluators,
        tests=[{"id": "t", "input": "say hi"}],
    )


def _runner(calls, llm=None):
    async def call(prompt, target):
        calls.append(prompt)
        return "hi there"

    return Runner(pm=make_manager(), call_agent=call, llm_adapter=llm)


@pytest.mark.parametrize("name", sorted(BAD_CONFIGS))
@pytest.mark.asyncio
async def test_bad_config_fails_run_before_any_call(name):
    cfg, needle = BAD_CONFIGS[name]
    calls: list[str] = []
    ds = _ds([{"name": name, **cfg}, {"name": "contains", "substring": "hi"}])
    with pytest.raises(EvaluatorConfigError) as exc:
        await _runner(calls).execute(ds)
    assert calls == []
    assert exc.value.evaluator == name
    assert repr(name) in str(exc.value) and needle in str(exc.value)


def test_every_audited_name_is_a_factory():
    assert set(BAD_CONFIGS) <= set(BUILTIN_EVALUATOR_FACTORIES)


@pytest.mark.asyncio
async def test_missing_required_key_names_the_key():
    class Adapter:
        async def complete(self, *a, **k):  # never reached
            raise AssertionError

    calls: list[str] = []
    with pytest.raises(EvaluatorConfigError, match="criteria"):
        await _runner(calls, llm=Adapter()).execute(_ds([{"name": "geval"}]))
    assert calls == []


@pytest.mark.asyncio
async def test_judge_without_adapter_is_a_skip_not_a_config_error():
    calls: list[str] = []
    run = await _runner(calls).execute(
        _ds([{"name": "task_completion"}, {"name": "contains", "substring": "hi"}])
    )
    assert calls == ["say hi"]
    assert [r.evaluator for r in run.results] == ["contains"]
    assert run.skipped and run.skipped[0].startswith("task_completion:")


@pytest.mark.asyncio
async def test_not_applicable_case_is_not_a_config_error():
    # key_facts with no facts on the case and none in config: scores nothing.
    calls: list[str] = []
    run = await _runner(calls).execute(_ds([{"name": "key_facts"}]))
    assert calls == ["say hi"]
    assert any("no evaluator applied" in s for s in run.skipped)


@pytest.mark.asyncio
async def test_key_facts_conflict_uses_the_same_error():
    calls: list[str] = []
    ds = _ds([{"name": "key_facts", "mode": "binary", "threshold": 0.5}])
    with pytest.raises(EvaluatorConfigError) as exc:
        await _runner(calls).execute(ds)
    assert isinstance(exc.value, KeyFactsConfigError)
    assert exc.value.evaluator == "key_facts" and calls == []


def test_errors_stay_value_errors():
    # Contract load (pydantic) and the gateway key off ValueError.
    assert issubclass(EvaluatorConfigError, ValueError)
    assert issubclass(JudgeAdapterRequired, ValueError)
    assert not issubclass(JudgeAdapterRequired, EvaluatorConfigError)
