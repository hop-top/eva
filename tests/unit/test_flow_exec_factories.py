# tests/unit/test_flow_exec_factories.py
"""Regression: flow-exec evaluators registered as built-in factories.

``core/evaluators/__init__.py:EVALUATOR_REGISTRY`` and
``core/evaluators/builtin.py:BUILTIN_EVALUATOR_FACTORIES`` are TWO
separate registries. The first is consumed by the YAML loader for
class-name resolution; the second is what the gateway
(``server/gateway/routes.py``) and the standalone CLI
(``cli/run_contract.py``) actually call at evaluation time.

When a contract uses ``name: status_code`` (or ``exit_code`` / ``equals``)
but the factory map is missing the entry, both call sites silent-skip
the evaluator: the lookup returns ``None``, the name is appended to a
``skipped`` list, and overall pass-fail is computed as if the
evaluator wasn't declared. This regression test asserts the factory
entries exist and produce working instances.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest

from core.evaluators.builtin import BUILTIN_EVALUATOR_FACTORIES
from core.evaluators.equals import EqualsEvaluator
from core.evaluators.status_code import StatusCodeEvaluator


@pytest.mark.parametrize("name", ["status_code", "exit_code", "equals"])
def test_factory_registered(name: str) -> None:
    assert name in BUILTIN_EVALUATOR_FACTORIES, (
        f"{name!r} missing from BUILTIN_EVALUATOR_FACTORIES — contracts "
        f"using this name will silent-skip in gateway / CLI"
    )


def test_status_code_factory_builds_with_expected() -> None:
    factory = BUILTIN_EVALUATOR_FACTORIES["status_code"]
    ev = factory({"step": "cli-version", "expected": 0}, None)
    assert isinstance(ev, StatusCodeEvaluator)
    assert hasattr(ev, "run")
    score = ev.run(json.dumps({"exit_code": 0}))
    assert score.value == 1.0


def test_status_code_factory_builds_with_expected_in() -> None:
    factory = BUILTIN_EVALUATOR_FACTORIES["status_code"]
    ev = factory({"step": "cli-version", "expected_in": [0, 2]}, None)
    score = ev.run(json.dumps({"exit_code": 2}))
    assert score.value == 1.0


def test_exit_code_factory_is_alias_for_status_code() -> None:
    # Both names build the same class (StatusCodeEvaluator); the
    # alias exists so YAML using ``name: exit_code`` resolves too.
    factory = BUILTIN_EVALUATOR_FACTORIES["exit_code"]
    ev = factory({"step": "cli-version", "expected": 0}, None)
    assert isinstance(ev, StatusCodeEvaluator)
    score = ev.run(json.dumps({"exit_code": 0}))
    assert score.value == 1.0


def test_status_code_factory_propagates_validation_errors() -> None:
    # Neither expected nor expected_in given — evaluator __init__
    # should raise rather than building a half-configured instance.
    factory = BUILTIN_EVALUATOR_FACTORIES["status_code"]
    with pytest.raises(ValueError, match="expected"):
        factory({"step": "cli-version"}, None)


def test_equals_factory_builds_with_field_and_expected() -> None:
    factory = BUILTIN_EVALUATOR_FACTORIES["equals"]
    ev = factory({"field": "log_level", "expected": "info"}, None)
    assert isinstance(ev, EqualsEvaluator)
    assert hasattr(ev, "run")
    score = ev.run(json.dumps({"log_level": "info"}))
    assert score.value == 1.0


def test_equals_factory_accepts_expected_none() -> None:
    # ``expected: null`` in YAML must NOT be conflated with "expected
    # missing"; the evaluator distinguishes via the _MISSING sentinel
    # and the factory preserves that distinction.
    factory = BUILTIN_EVALUATOR_FACTORIES["equals"]
    ev = factory({"field": "optional", "expected": None}, None)
    score = ev.run(json.dumps({"optional": None}))
    assert score.value == 1.0


def test_equals_factory_propagates_missing_expected() -> None:
    # ``field`` set, ``expected`` absent — evaluator should raise.
    factory = BUILTIN_EVALUATOR_FACTORIES["equals"]
    with pytest.raises(ValueError, match="expected"):
        factory({"field": "log_level"}, None)


def test_equals_factory_propagates_missing_field() -> None:
    factory = BUILTIN_EVALUATOR_FACTORIES["equals"]
    with pytest.raises(ValueError, match="field"):
        factory({"expected": "info"}, None)


# --- CLI smoke test: status_code / exit_code / equals no longer silent-skip ---

def _run_eva(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        capture_output=True,
        text=True,
        input=stdin,
    )


def _write(path: Path, body: str) -> Path:
    path.write_text(dedent(body).lstrip())
    return path


def test_cli_status_code_no_longer_silent_skipped(tmp_path: Path) -> None:
    """End-to-end: contract using ``name: status_code`` must produce an
    outcome, not appear in ``skipped`` (regression for PR #2 review).
    """
    contract = _write(
        tmp_path / "c.yaml",
        """
        name: flow-step-ok
        provider: noop
        evaluators:
          - name: status_code
            step: cli-version
            expected: 0
        """,
    )
    inp = _write(tmp_path / "in.json", '{"exit_code": 0, "stdout": "v1"}')

    result = _run_eva(
        "run", "--contract", str(contract), "--input", str(inp), "--format", "json"
    )
    assert result.returncode == 0, f"stderr={result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    # The critical assertion: NOT in skipped.
    assert payload["skipped"] == []
    assert payload["evaluators"][0]["name"] == "status_code"
    assert payload["evaluators"][0]["passed"] is True


def test_cli_exit_code_alias_no_longer_silent_skipped(tmp_path: Path) -> None:
    contract = _write(
        tmp_path / "c.yaml",
        """
        name: flow-step-alias
        provider: noop
        evaluators:
          - name: exit_code
            step: cli-version
            expected_in: [0, 2]
        """,
    )
    inp = _write(tmp_path / "in.json", '{"exit_code": 2}')

    result = _run_eva(
        "run", "--contract", str(contract), "--input", str(inp), "--format", "json"
    )
    assert result.returncode == 0, f"stderr={result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["skipped"] == []
    assert payload["evaluators"][0]["name"] == "exit_code"


def test_cli_equals_no_longer_silent_skipped(tmp_path: Path) -> None:
    contract = _write(
        tmp_path / "c.yaml",
        """
        name: flow-step-equals
        provider: noop
        evaluators:
          - name: equals
            field: log_level
            expected: info
        """,
    )
    inp = _write(tmp_path / "in.json", '{"log_level": "info"}')

    result = _run_eva(
        "run", "--contract", str(contract), "--input", str(inp), "--format", "json"
    )
    assert result.returncode == 0, f"stderr={result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["skipped"] == []
    assert payload["evaluators"][0]["name"] == "equals"
    assert payload["evaluators"][0]["passed"] is True
