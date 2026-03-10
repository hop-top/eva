# server/gateway/retry.py — retry + self-healing engine
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable
from core.models import Contract
from server.gateway.evaluator import evaluate_response, EvaluationResult


@dataclass
class RetryResult:
    response_text: str
    attempts: int
    passed: bool
    violations: list[dict] = field(default_factory=list)
    eval_result: EvaluationResult | None = None


class RetryExhausted(Exception):
    def __init__(self, attempts: int, violations: list[dict], last_response: str) -> None:
        super().__init__(
            f"Contract violated after {attempts} attempt(s): {violations}"
        )
        self.attempts = attempts
        self.violations = violations
        self.last_response = last_response


async def retry_with_hint(
    agent_fn: Callable[[dict], Awaitable[str]],
    initial_body: dict,
    contract: Contract,
    evaluator_map: dict,
    context: dict,
) -> RetryResult:
    """
    Call agent_fn, evaluate the response, retry up to max_retries times on failure.
    On each retry, injects contract.retry_policy.hint as `_eva_hint` in the request body.
    Raises RetryExhausted if all attempts fail.
    """
    policy = contract.retry_policy
    max_attempts = 1 + policy.max_retries
    body = dict(initial_body)
    eval_result = None
    response_text = ""

    for attempt in range(1, max_attempts + 1):
        if attempt > 1 and policy.hint:
            body["_eva_hint"] = policy.hint

        if attempt > 1 and policy.backoff_ms > 0:
            await asyncio.sleep(policy.backoff_ms / 1000)

        response_text = await agent_fn(body)
        eval_result = await evaluate_response(
            response_text=response_text,
            contract=contract,
            context={**context, "attempt": attempt},
            evaluator_map=evaluator_map,
        )

        if eval_result.passed:
            return RetryResult(
                response_text=response_text,
                attempts=attempt,
                passed=True,
                violations=[],
                eval_result=eval_result,
            )

    raise RetryExhausted(
        attempts=max_attempts,
        violations=eval_result.violations if eval_result else [],
        last_response=response_text,
    )
