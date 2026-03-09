# server/gateway/evaluator.py — inline/sync response evaluator
from __future__ import annotations
import time
from dataclasses import dataclass, field
from core.models import Contract, Result, Score


@dataclass
class EvaluationResult:
    passed: bool
    violations: list[dict] = field(default_factory=list)
    results: list[Result] = field(default_factory=list)


async def evaluate_response(
    response_text: str,
    contract: Contract,
    context: dict,
    evaluator_map: dict | None = None,
) -> EvaluationResult:
    """Run all evaluators in contract against response_text. Returns EvaluationResult."""
    if evaluator_map is None:
        evaluator_map = {}

    violations: list[dict] = []
    results: list[Result] = []

    for ref in contract.evaluators:
        evaluator = evaluator_map.get(ref.name)
        if evaluator is None:
            # Unknown evaluator — skip gracefully
            continue

        t0 = time.monotonic()
        score: Score = evaluator._run(response_text)
        duration_ms = int((time.monotonic() - t0) * 1000)

        result = Result(
            test_id=context.get("request_id", "unknown"),
            evaluator=ref.name,
            score=score,
            mode=ref.mode,
            min_score=ref.min_score,
            duration_ms=duration_ms,
            trace_id=context.get("trace_id"),
        )
        results.append(result)

        if not result.passed:
            violations.append(
                {
                    "evaluator": ref.name,
                    "score": score.value,
                    "reason": score.reason,
                }
            )

    return EvaluationResult(
        passed=len(violations) == 0,
        violations=violations,
        results=results,
    )
