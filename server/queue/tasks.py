# server/queue/tasks.py — ARQ async evaluation task
from __future__ import annotations
from core.models import Contract
from server.gateway.evaluator import evaluate_response
from server.gateway.routes import _build_evaluator_map, EvaluatorSpec


async def evaluate_async(
    ctx: dict,
    response_text: str,
    contract_dict: dict,
    evaluator_specs: list[dict],
    context: dict,
) -> dict:
    """
    ARQ task: evaluate a response against a contract asynchronously.
    Called fire-and-forget; result is stored in ARQ job store.
    ctx is the ARQ context dict (contains redis connection, job_id, etc.).
    """
    contract = Contract.model_validate(contract_dict)
    specs = [EvaluatorSpec(**s) for s in evaluator_specs]
    evaluator_map = _build_evaluator_map(specs)

    eval_result = await evaluate_response(
        response_text=response_text,
        contract=contract,
        context=context,
        evaluator_map=evaluator_map,
    )

    return {
        "passed": eval_result.passed,
        "violations": eval_result.violations,
        "request_id": context.get("request_id"),
    }
