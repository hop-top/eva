"""A bad non-judge evaluator config in a contract is a config error.

Same mechanism as dataset runs (``EvaluatorConfigError``): never mistaken for
"no judge model configured", which is only for judge evaluators without an adapter.
"""
from __future__ import annotations

import io
from pathlib import Path
from textwrap import dedent

import pytest
import yaml

from cli.run_contract import EXIT_BAD_INPUT, evaluate_contract, run_contract_cli
from core.contract import ContractValidationError, load_contract


def _write(path: Path, body: str) -> Path:
    path.write_text(dedent(body).lstrip())
    return path


BAD = {
    "mood": ({"expected": "grumpy"}, "grumpy"),
    "language": ({"expected": "klingon"}, "klingon"),
    "regex": ({"pattern": "("}, "'('"),
    "json_path": ({"path": "$.a", "comparator": "approx"}, "approx"),
    "ifeval_check": ({"pass_on": "sloppy"}, "sloppy"),
}


def _contract(tmp_path, name: str) -> Path:
    cfg, _ = BAD[name]
    return _write(
        tmp_path / "c.yaml",
        yaml.dump({
            "name": "bad",
            "provider": "noop",
            "evaluators": [
                {"name": "contains", "substring": "hi"},
                {"name": name, **cfg},
            ],
        }),
    )


@pytest.mark.parametrize("name", sorted(BAD))
def test_load_contract_names_evaluator_and_value(tmp_path, name):
    with pytest.raises(ContractValidationError) as exc:
        load_contract(_contract(tmp_path, name))
    msg = str(exc.value)
    assert msg.startswith(f"evaluator {name!r}: "), msg
    assert BAD[name][1] in msg
    assert "no judge model" not in msg


@pytest.mark.parametrize("name", sorted(BAD))
def test_run_contract_exits_2_with_real_message(tmp_path, name):
    out, err = io.StringIO(), io.StringIO()
    inp = tmp_path / "in.txt"
    inp.write_text("hi")
    code = run_contract_cli(
        _contract(tmp_path, name), str(inp), "text", False, stdout=out, stderr=err
    )
    assert code == EXIT_BAD_INPUT
    assert f"evaluator {name!r}: " in err.getvalue()
    assert BAD[name][1] in err.getvalue()
    assert out.getvalue() == ""


def test_evaluate_contract_raises_config_error(tmp_path):
    with pytest.raises(ValueError, match="evaluator 'mood': .*grumpy"):
        evaluate_contract(_contract(tmp_path, "mood"), "hi")


def test_runner_builds_through_the_same_mechanism(tmp_path, monkeypatch):
    # Independent of the load-time check: the runner's own build must not
    # report a bad config as a judge skip.
    from core.evaluators.errors import EvaluatorConfigError

    monkeypatch.setattr("core.contract.check_evaluator_configs", lambda c: None)
    with pytest.raises(EvaluatorConfigError, match="evaluator 'mood': .*grumpy"):
        evaluate_contract(_contract(tmp_path, "mood"), "hi")


def test_judge_without_adapter_still_skips_with_its_reason(tmp_path):
    c = _write(
        tmp_path / "j.yaml",
        """
        name: j
        provider: noop
        evaluators:
          - name: relevance
          - name: contains
            substring: hi
        """,
    )
    assert load_contract(c).name == "j"
    report = evaluate_contract(c, "hi")
    assert report.skipped_judge == ["relevance: no judge model configured"]
    assert [o.name for o in report.outcomes] == ["contains"]


def test_valid_config_loads(tmp_path):
    c = _write(
        tmp_path / "ok.yaml",
        """
        name: ok
        provider: noop
        evaluators:
          - {name: mood, expected: imperative}
          - {name: regex, pattern: "a+"}
          - {name: nonexistent_evaluator}
        """,
    )
    assert len(load_contract(c).evaluators) == 3
