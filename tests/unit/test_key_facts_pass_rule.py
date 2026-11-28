"""key_facts' derived pass rule (threshold -> mode/min_score) on every path.

Dataset runs, ``eva run --contract`` and contract loading (shared by the
gateway) must agree; evaluators without a rule keep their defaults.
"""
from __future__ import annotations

import io
from textwrap import dedent

import pytest

from cli.run_contract import EXIT_BAD_INPUT, EXIT_EVAL_FAIL, EXIT_PASS, run_contract_cli
from core.contract import ContractValidationError, load_contract
from core.dataset import Dataset
from core.evaluators.key_facts import KeyFactsConfigError
from core.evaluators.pass_rules import with_default_pass_rule
from core.models import EvaluatorRef
from core.plugins import make_manager
from core.runner import Runner

FACTS = '["Paris", "1889", "330 m", "Gustave Eiffel"]'
THREE_OF_FOUR = "Paris, 1889, 330 m."


def contract(tmp_path, evaluator_yaml: str):
    p = tmp_path / "c.yaml"
    p.write_text(
        "name: c\nprovider: noop\nevaluators:\n" + dedent(evaluator_yaml).strip("\n") + "\n"
    )
    return p


def key_facts_yaml(extra: str = "") -> str:
    body = f"  - name: key_facts\n    required: {FACTS}\n"
    if extra:
        body += "".join(f"    {line}\n" for line in extra.strip().splitlines())
    return body


def run_cli(path, text):
    inp = path.parent / "in.txt"
    inp.write_text(text)
    out, err = io.StringIO(), io.StringIO()
    code = run_contract_cli(path, str(inp), "json", False, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


# --- the hook itself -----------------------------------------------------------


def test_no_rule_for_other_evaluators():
    cfg = {"name": "contains", "substring": "x"}
    assert with_default_pass_rule(cfg) is cfg
    ref = EvaluatorRef(name="contains", substring="x")
    assert (ref.mode, ref.min_score) == ("binary", 1.0)
    assert not {"mode", "min_score"} & ref.model_fields_set


def test_ref_derives_rule_when_user_set_nothing():
    ref = EvaluatorRef(name="key_facts", threshold=0.75)
    assert (ref.mode, ref.min_score) == ("threshold", 0.75)
    ref = EvaluatorRef(name="key_facts")
    assert (ref.mode, ref.min_score) == ("threshold", 1.0)


@pytest.mark.parametrize("mode", ["binary", "warn"])
def test_ref_explicit_mode_is_kept(mode):
    ref = EvaluatorRef(name="key_facts", mode=mode)
    assert ref.mode == mode and ref.min_score == 1.0


def test_ref_explicit_min_score_wins_and_implies_threshold_mode():
    ref = EvaluatorRef(name="key_facts", min_score=0.5)
    assert (ref.mode, ref.min_score) == ("threshold", 0.5)
    ref = EvaluatorRef(name="key_facts", mode="threshold", threshold=0.5)
    assert ref.min_score == 0.5


def test_ref_is_idempotent_on_revalidation():
    ref = EvaluatorRef(name="key_facts", threshold=0.75)
    again = EvaluatorRef.model_validate(ref.model_dump())
    assert (again.mode, again.min_score) == ("threshold", 0.75)


@pytest.mark.parametrize(
    "kw",
    [
        {"mode": "binary", "threshold": 0.75},
        {"min_score": 0.5, "threshold": 0.75},
        {"mode": "threshold", "min_score": 0.5, "threshold": 0.75},
    ],
)
def test_conflicts_raise(kw):
    with pytest.raises(ValueError, match="conflicts"):
        EvaluatorRef(name="key_facts", **kw)
    with pytest.raises(KeyFactsConfigError):
        with_default_pass_rule({"name": "key_facts", **kw})


# --- eva run --contract -----------------------------------------------------------


def test_contract_mode_threshold_passes_three_of_four(tmp_path):
    p = contract(tmp_path, key_facts_yaml("threshold: 0.75"))
    code, out, _ = run_cli(p, THREE_OF_FOUR)
    assert code == EXIT_PASS, out
    assert '"mode": "threshold"' in out and '"score": 0.75' in out


def test_contract_mode_default_needs_every_fact(tmp_path):
    code, _, err = run_cli(contract(tmp_path, key_facts_yaml()), THREE_OF_FOUR)
    assert code == EXIT_EVAL_FAIL
    assert '"score": 0.75' in err


def test_contract_mode_conflict_exits_2_with_message(tmp_path):
    p = contract(tmp_path, key_facts_yaml("mode: binary\nthreshold: 0.75"))
    code, _, err = run_cli(p, THREE_OF_FOUR)
    assert code == EXIT_BAD_INPUT
    assert "conflicts with mode: binary" in err


def test_contract_mode_explicit_binary_still_binary(tmp_path):
    p = contract(tmp_path, key_facts_yaml("mode: binary"))
    assert run_cli(p, THREE_OF_FOUR)[0] == EXIT_EVAL_FAIL


def test_contract_mode_other_evaluator_unchanged(tmp_path):
    p = contract(tmp_path, "  - name: contains\n    substring: Paris\n")
    code, out, _ = run_cli(p, "Paris")
    assert code == EXIT_PASS and '"mode": "binary"' in out and '"min_score": 1.0' in out


def test_load_contract_conflict_is_validation_error(tmp_path):
    p = contract(tmp_path, key_facts_yaml("min_score: 0.5\nthreshold: 0.75"))
    with pytest.raises(ContractValidationError, match="conflicts"):
        load_contract(p)


# --- dataset runs -----------------------------------------------------------------


def _ds(evaluator):
    return Dataset(
        name="d",
        target="http://x",
        evaluators=[evaluator],
        tests=[{"id": "t", "input": "s", "metadata": {"key_facts": {"required": ["Paris", "1889", "330 m", "Eiffel"]}}}],
    )


async def _run(ds):
    async def call(i, t):
        return THREE_OF_FOUR

    return await Runner(pm=make_manager(), call_agent=call).execute(ds)


@pytest.mark.asyncio
async def test_dataset_threshold_passes_with_true_coverage():
    run = await _run(_ds({"name": "key_facts", "threshold": 0.75}))
    r = run.results[0]
    assert r.passed and r.score.value == 0.75 and r.mode == "threshold"


@pytest.mark.asyncio
async def test_dataset_default_needs_all_facts():
    run = await _run(_ds({"name": "key_facts"}))
    assert not run.results[0].passed and run.results[0].min_score == 1.0


@pytest.mark.asyncio
async def test_dataset_explicit_mode_wins():
    run = await _run(_ds({"name": "key_facts", "mode": "warn"}))
    assert run.results[0].passed and run.results[0].mode == "warn"


@pytest.mark.asyncio
async def test_dataset_conflict_fails_run_not_silent_skip():
    with pytest.raises(KeyFactsConfigError):
        await _run(_ds({"name": "key_facts", "mode": "binary", "threshold": 0.5}))
