# cli/run_contract.py
"""Standalone contract evaluation — `eva run --contract <file> --input <file>`.

No gateway, no agent call. Loads a contract YAML + an input artifact, runs
each contract evaluator against the input, returns exit 0 on full pass and
exit 1 on any failure (exit 2 on bad input/yaml/io).

Reuses the same built-in evaluator dispatch as the gateway
(`core.evaluators.builtin`) so behaviour matches `POST /v1/contract/invoke`.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from core.contract import ContractValidationError, load_contract
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
    # judge-based evaluators not run, as "<name>: <reason>"
    skipped_judge: list[str] = field(default_factory=list)

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
                "skipped_judge": self.skipped_judge,
            },
            indent=2,
        )


def _load_text(path_or_dash: str, what: str) -> str:
    """Load text from file path or stdin (`-`).

    Raises ValueError if the text is not valid UTF-8 (binary file or wrong
    encoding) — caught by run_contract_cli and surfaced as EXIT_BAD_INPUT.
    """
    if path_or_dash == "-":
        try:
            return sys.stdin.read()
        except UnicodeDecodeError as e:
            raise ValueError(
                f"stdin {what} is not valid UTF-8 text: {e}"
            ) from e
    path = Path(path_or_dash)
    if not path.exists():
        raise FileNotFoundError(f"{what.capitalize()} file not found: {path_or_dash}")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise ValueError(
            f"{what} file '{path}' is not valid UTF-8 text: {e}"
        ) from e


def _load_input(input_path: str) -> str:
    """Load the response artifact (file path or stdin `-`)."""
    return _load_text(input_path, "input")


def _passed(score: float, mode: str, min_score: float) -> bool:
    """Decide pass/fail per evaluator mode.

    NOTE: keep in sync with core/models.py::Result.compute_passed
    (the canonical pass-decision used by the gateway via the Result
    pydantic model). This duplicate exists to avoid pulling pydantic
    + the eva[server] extras into the standalone CLI. If you change
    either, update both.
    """
    if mode == "warn":
        return True
    if mode == "threshold":
        return score >= min_score
    # binary (default)
    return score == 1.0


# Judge evaluators (factories that need an llm_adapter) split by what they read
# beyond (prompt, response). A contract run supplies nothing else, so those in
# JUDGE_NEEDS are skipped with a precise reason instead of guessing inputs.
JUDGE_PROMPT_ONLY = frozenset({
    "relevance", "hallucination", "tone", "task_completion", "safety",
    "plan_quality", "geval", "rag:answer_relevancy", "rag:faithfulness",
    "content:bias", "content:toxicity", "content:summarization",
    "content:prompt_alignment",
})
# name -> (needed input, config key that supplies it, if any)
JUDGE_NEEDS: dict[str, tuple[str, str | None]] = {
    "tool_correctness": ("tool events", None),
    "argument_correctness": ("tool events", None),
    "tool_use": ("tool events", None),
    "step_efficiency": ("tool events", None),
    "plan_adherence": ("planned steps", None),
    "rag:contextual_relevancy": ("retrieval context", None),
    "rag:contextual_precision": ("retrieval context", None),
    "rag:contextual_recall": ("retrieval context", None),
    "ragas": ("retrieval context", None),
    "content:goal_accuracy": ("expected output", "expected_output"),
}

NO_JUDGE_REASON = "no judge model configured"
NO_PROMPT_REASON = (
    "judge evaluators need the request prompt: pass --prompt or --prompt-file"
)


def _missing_input_reason(name: str, cfg: dict) -> str | None:
    need = JUDGE_NEEDS.get(name)
    if need is None or (need[1] and cfg.get(need[1])):
        return None
    return (
        f"needs {need[0]}, which a contract run cannot supply "
        "(use dataset mode)"
        if not need[1]
        else f"needs {need[0]}: set `{need[1]}` in the contract, or use dataset mode"
    )


async def _run_judges(jobs: list[tuple[Any, str]], prompt: str):
    """Run judge evaluators in one event loop; a failed call yields a 0.0 Score."""
    results = []
    for ev, response_text in jobs:
        t0 = time.monotonic()
        try:
            score = await ev.evaluate(prompt=prompt, response=response_text)
        except Exception as e:  # endpoint down, timeout, auth, ...
            msg = (str(e).strip().splitlines() or [""])[0]
            score = Score(
                value=0.0,
                reason=f"judge error: {type(e).__name__}: {msg}".rstrip(": "),
            )
        results.append((score, int((time.monotonic() - t0) * 1000)))
    return results


def _outcome(ref, score: Score, dur_ms: int) -> EvaluatorOutcome:
    return EvaluatorOutcome(
        name=ref.name,
        mode=ref.mode,
        min_score=ref.min_score,
        score=score.value,
        passed=_passed(score.value, ref.mode, ref.min_score),
        reason=score.reason,
        duration_ms=dur_ms,
    )


def evaluate_contract(
    contract_path: Path,
    response_text: str,
    llm_adapter: Any = None,
    prompt: str | None = None,
) -> ContractRunReport:
    """Run all evaluators in `contract_path` against `response_text`.

    Returns a ContractRunReport with one outcome per recognised evaluator.
    Unknown evaluators (no factory) are recorded under `skipped`. Judge-based
    evaluators run when `llm_adapter` and `prompt` are both given and the
    evaluator needs nothing else; otherwise they land under `skipped_judge`
    with a reason.
    """
    # YAMLError → ValueError so callers see a uniform "bad input" exception
    # (load_contract lets YAMLError bubble; CLI layer maps ValueError → exit 2).
    try:
        contract = load_contract(contract_path)
    except yaml.YAMLError as e:
        raise ValueError(f"Malformed contract YAML: {e}") from e
    except ContractValidationError as e:
        raise ValueError(str(e)) from e

    started = time.monotonic()

    skipped: list[str] = []
    skipped_judge: list[str] = []
    # Slots keep contract order: a finished EvaluatorOutcome, or a pending
    # (ref, evaluator) judge job filled in after the judge calls ran.
    slots: list[Any] = []
    jobs: list[tuple[Any, str]] = []

    # One evaluator per ref (duplicate names with distinct configs supported —
    # e.g. two `contains` checks with different substrings). Per-evaluator
    # config (substring, pattern, schema, …) flows via __pydantic_extra__
    # since EvaluatorRef sets extra="allow" (T-0260) — same path as gateway.
    for ref in contract.evaluators:
        factory = BUILTIN_EVALUATOR_FACTORIES.get(ref.name)
        if factory is None:
            skipped.append(ref.name)
            continue
        cfg = ref.__pydantic_extra__ or {}
        # Judge-based factories raise ValueError without an adapter (see
        # core/evaluators/builtin.py:_require_llm). Probe without one so
        # non-judge evaluators (incl. prose_assertion) behave as before.
        try:
            ev = factory(cfg, None)
        except ValueError as e:
            if llm_adapter is None:
                skipped_judge.append(f"{ref.name}: {NO_JUDGE_REASON}")
                continue
            if ref.name not in JUDGE_PROMPT_ONLY and ref.name not in JUDGE_NEEDS:
                # Unclassified: never guess inputs for it.
                skipped_judge.append(f"{ref.name}: {e}")
                continue
            why = _missing_input_reason(ref.name, cfg)
            if why is None and prompt is None:
                why = NO_PROMPT_REASON
            if why is not None:
                skipped_judge.append(f"{ref.name}: {why}")
                continue
            try:
                ev = factory(cfg, llm_adapter)
            except (KeyError, TypeError) as e:
                skipped_judge.append(f"{ref.name}: invalid evaluator config ({e})")
                continue
            slots.append((ref, len(jobs)))
            jobs.append((ev, response_text))
            continue
        t0 = time.monotonic()
        score: Score = ev.run(response_text)
        dur_ms = int((time.monotonic() - t0) * 1000)
        slots.append(_outcome(ref, score, dur_ms))

    judged = asyncio.run(_run_judges(jobs, prompt)) if jobs else []
    outcomes: list[EvaluatorOutcome] = []
    for slot in slots:
        if isinstance(slot, EvaluatorOutcome):
            outcomes.append(slot)
        else:
            ref, idx = slot
            score, dur_ms = judged[idx]
            outcomes.append(_outcome(ref, score, dur_ms))
    overall_pass = all(o.passed for o in outcomes)

    total_ms = int((time.monotonic() - started) * 1000)
    return ContractRunReport(
        contract=contract.name,
        passed=overall_pass,
        duration_ms=total_ms,
        outcomes=outcomes,
        skipped=skipped,
        skipped_judge=skipped_judge,
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
    for entry in report.skipped_judge:
        name, _, reason = entry.partition(": ")
        lines.append(f"  skipped: {name} ({reason})")
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
    prompt: str | None = None,
    prompt_file: str | None = None,
) -> int:
    """Entry point used by `cli/main.py` and tests. Returns the exit code.

    `prompt` / `prompt_file` (`-` = stdin) give judge evaluators the request
    prompt; at most one of them.
    """
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr

    try:
        if prompt is not None and prompt_file is not None:
            raise ValueError("--prompt and --prompt-file are mutually exclusive")
        if prompt_file is not None:
            if prompt_file == "-" and input_path == "-":
                raise ValueError(
                    "--prompt-file - and --input - both read stdin; use a file for one"
                )
            prompt = _load_text(prompt_file, "prompt file")
        if prompt is not None and not prompt.strip():
            raise ValueError("prompt is empty")
    except FileNotFoundError as e:
        print(f"Error: {e}", file=err)
        return EXIT_BAD_INPUT
    except ValueError as e:
        print(f"Error: {e}", file=err)
        return EXIT_BAD_INPUT
    except OSError as e:
        print(f"Error reading prompt: {e}", file=err)
        return EXIT_BAD_INPUT

    try:
        response_text = _load_input(input_path)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=err)
        return EXIT_BAD_INPUT
    except ValueError as e:
        # Raised by _load_input on UnicodeDecodeError (binary input).
        print(f"Error: {e}", file=err)
        return EXIT_BAD_INPUT
    except OSError as e:
        print(f"Error reading input: {e}", file=err)
        return EXIT_BAD_INPUT

    try:
        from core.config import find_and_load_config
        from core.llm import build_llm_adapter

        llm_adapter = build_llm_adapter(find_and_load_config())
        report = evaluate_contract(
            contract, response_text, llm_adapter=llm_adapter, prompt=prompt
        )
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
