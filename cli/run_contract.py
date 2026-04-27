# cli/run_contract.py
"""Standalone contract evaluation — `eva run --contract <file> --input <file>`.

No gateway, no agent call. Loads a contract YAML + an input artifact, runs
each contract evaluator against the input, returns exit 0 on full pass and
exit 1 on any failure (exit 2 on bad input/yaml/io).

Reuses the same built-in evaluator dispatch as the gateway
(`core.evaluators.builtin`) so behaviour matches `POST /v1/contract/invoke`.
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from core.evaluators.builtin import BUILTIN_EVALUATOR_FACTORIES
from core.models import Score


EXIT_PASS = 0
EXIT_EVAL_FAIL = 1
EXIT_BAD_INPUT = 2


@dataclass
class EvaluatorOutcome:
    name: str
    mode: str
    min_score: float
    score: float
    passed: bool
    reason: str | None
    duration_ms: int


@dataclass
class ContractRunReport:
    contract: str
    passed: bool
    duration_ms: int
    outcomes: list[EvaluatorOutcome] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            {
                "contract": self.contract,
                "passed": self.passed,
                "duration_ms": self.duration_ms,
                "evaluators": [
                    {
                        "name": o.name,
                        "mode": o.mode,
                        "min_score": o.min_score,
                        "score": o.score,
                        "passed": o.passed,
                        "reason": o.reason,
                        "duration_ms": o.duration_ms,
                    }
                    for o in self.outcomes
                ],
                "skipped": self.skipped,
            },
            indent=2,
        )


def _load_input(input_path: str) -> str:
    """Load input from file path or stdin (`-`). Returns raw text."""
    if input_path == "-":
        return sys.stdin.read()
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    return path.read_text()


def _load_contract_raw(contract_path: Path) -> dict[str, Any]:
    """Load + minimally validate a contract YAML. Returns raw dict (preserves
    evaluator config keys that the pydantic Contract model would drop)."""
    if not contract_path.exists():
        raise FileNotFoundError(f"Contract file not found: {contract_path}")
    try:
        raw = yaml.safe_load(contract_path.read_text())
    except yaml.YAMLError as e:
        raise ValueError(f"Malformed contract YAML: {e}") from e
    if not isinstance(raw, dict):
        raise ValueError("Contract YAML must be a mapping")
    if "name" not in raw:
        raise ValueError("Contract must have a 'name' field")
    raw.setdefault("evaluators", [])
    if not isinstance(raw["evaluators"], list):
        raise ValueError("Contract 'evaluators' must be a list")
    return raw


def _passed(score: float, mode: str, min_score: float) -> bool:
    if mode == "warn":
        return True
    if mode == "threshold":
        return score >= min_score
    # binary (default)
    return score == 1.0


def evaluate_contract(contract_path: Path, response_text: str) -> ContractRunReport:
    """Run all evaluators in `contract_path` against `response_text`.

    Returns a ContractRunReport with one outcome per recognised evaluator.
    Unknown evaluators (no factory) are recorded under `skipped`.
    """
    raw = _load_contract_raw(contract_path)
    name = raw["name"]
    eval_specs: list[dict] = raw["evaluators"]

    started = time.monotonic()

    outcomes: list[EvaluatorOutcome] = []
    skipped: list[str] = []
    overall_pass = True

    # Build one evaluator per spec (preserves duplicate names with distinct
    # configs — e.g. two `contains` checks with different substrings).
    for spec in eval_specs:
        ev_name = spec.get("name", "")
        mode = spec.get("mode", "binary")
        min_score = float(spec.get("min_score", 1.0))
        factory = BUILTIN_EVALUATOR_FACTORIES.get(ev_name)
        if factory is None:
            skipped.append(ev_name)
            continue
        ev = factory(spec)
        t0 = time.monotonic()
        score: Score = ev._run(response_text)
        dur_ms = int((time.monotonic() - t0) * 1000)
        passed = _passed(score.value, mode, min_score)
        if not passed:
            overall_pass = False
        outcomes.append(
            EvaluatorOutcome(
                name=ev_name,
                mode=mode,
                min_score=min_score,
                score=score.value,
                passed=passed,
                reason=score.reason,
                duration_ms=dur_ms,
            )
        )

    total_ms = int((time.monotonic() - started) * 1000)
    return ContractRunReport(
        contract=name,
        passed=overall_pass,
        duration_ms=total_ms,
        outcomes=outcomes,
        skipped=skipped,
    )


def _format_text(report: ContractRunReport, quiet: bool) -> str:
    """Human-readable output. Mirrors `eva run --no-tui` style."""
    lines: list[str] = []
    lines.append(f"Contract: {report.contract}")
    for o in report.outcomes:
        if quiet and o.passed:
            continue
        icon = "PASS" if o.passed else "FAIL"
        head = f"  [{icon}] {o.name} (mode={o.mode}, score={o.score:.2f}, {o.duration_ms}ms)"
        lines.append(head)
        if o.reason and not o.passed:
            lines.append(f"    reason: {o.reason}")
    if report.skipped:
        lines.append(f"  skipped (no factory): {', '.join(report.skipped)}")
    status = "PASSED" if report.passed else "FAILED"
    n_pass = sum(1 for o in report.outcomes if o.passed)
    lines.append(f"\n{status}  {n_pass}/{len(report.outcomes)} evaluators  ({report.duration_ms}ms)")
    return "\n".join(lines)


def run_contract_cli(
    contract: Path,
    input_path: str,
    fmt: str,
    quiet: bool,
    stdout=None,
    stderr=None,
) -> int:
    """Entry point used by `cli/main.py` and tests. Returns the exit code."""
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr

    try:
        response_text = _load_input(input_path)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=err)
        return EXIT_BAD_INPUT
    except OSError as e:
        print(f"Error reading input: {e}", file=err)
        return EXIT_BAD_INPUT

    try:
        report = evaluate_contract(contract, response_text)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=err)
        return EXIT_BAD_INPUT
    except ValueError as e:
        print(f"Error: {e}", file=err)
        return EXIT_BAD_INPUT

    if fmt == "json":
        # JSON always to the report sink: stdout on pass, stderr on fail
        # (so CI scripts can pipe stdout safely on success).
        sink = out if report.passed else err
        print(report.to_json(), file=sink)
    else:
        text = _format_text(report, quiet=quiet)
        sink = out if report.passed else err
        print(text, file=sink)

    return EXIT_PASS if report.passed else EXIT_EVAL_FAIL
