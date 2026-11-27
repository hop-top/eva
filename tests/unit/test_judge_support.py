"""Shared judge helpers used by contract mode and the gateway."""
from __future__ import annotations

import pytest

from core.evaluators.builtin import BUILTIN_EVALUATOR_FACTORIES
from core.evaluators.judge_support import (
    JUDGE_NEEDS,
    JUDGE_PROMPT_ONLY,
    NO_JUDGE_REASON,
    build_judge,
    judge_skip_reason,
    run_judge,
)


class _Adapter:
    pass


def _err(name):
    try:
        BUILTIN_EVALUATOR_FACTORIES[name]({}, None)
    except ValueError as e:
        return e
    raise AssertionError(f"{name} is not a judge evaluator")


def test_classification_lives_in_core_and_cli_reexports_it():
    import cli.run_contract as rc

    assert rc.JUDGE_PROMPT_ONLY is JUDGE_PROMPT_ONLY
    assert rc.JUDGE_NEEDS is JUDGE_NEEDS


def test_no_adapter_wins_over_everything():
    assert (
        judge_skip_reason("tool_use", {}, _err("tool_use"), None, "the gateway")
        == NO_JUDGE_REASON
    )


def test_runnable_judge_has_no_skip_reason():
    assert judge_skip_reason("relevance", {}, _err("relevance"), _Adapter(), "x") is None


def test_needs_reason_names_the_runner():
    why = judge_skip_reason("ragas", {}, _err("ragas"), _Adapter(), "the gateway")
    assert why == (
        "needs retrieval context, which the gateway cannot supply (use dataset mode)"
    )
    why = judge_skip_reason("ragas", {}, _err("ragas"), _Adapter(), "a contract run")
    assert "which a contract run cannot supply" in why


def test_config_key_supplies_the_input():
    name = "content:goal_accuracy"
    assert "expected_output" in judge_skip_reason(
        name, {}, _err(name), _Adapter(), "the gateway"
    )
    assert judge_skip_reason(
        name, {"expected_output": "x"}, _err(name), _Adapter(), "the gateway"
    ) is None


def test_unclassified_judge_is_skipped_with_factory_error():
    err = ValueError("evaluator 'newjudge' requires an llm_adapter; none was provided")
    assert judge_skip_reason("newjudge", {}, err, _Adapter(), "x") == str(err)


def test_build_judge_reports_invalid_config():
    def factory(cfg, llm):
        return cfg["missing"]

    ev, why = build_judge(factory, {}, _Adapter())
    assert ev is None and why.startswith("invalid evaluator config (")


@pytest.mark.asyncio
async def test_run_judge_turns_failures_into_a_zero_score():
    class Boom:
        async def evaluate(self, prompt, response):
            raise RuntimeError("down\nmore")

    score = await run_judge(Boom(), "p", "r")
    assert score.value == 0.0 and score.reason == "judge error: RuntimeError: down"


@pytest.mark.asyncio
async def test_run_judge_passes_prompt_and_response():
    from core.models import Score

    class Ok:
        async def evaluate(self, prompt, response):
            return Score(value=1.0, reason=f"{prompt}|{response}")

    assert (await run_judge(Ok(), "P", "R")).reason == "P|R"
