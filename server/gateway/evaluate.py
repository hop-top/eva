# server/gateway/evaluate.py — POST /v1/contract/evaluate handler
"""Score output the caller already holds against a named contract.

The evaluate-only twin of `contract_invoke`: same evaluators, same thresholds,
same judge skip rules, but no provider call, no retry, no request_schema check
and nothing persisted. Wired into the /v1 router in `server.gateway.routes`.
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from server.gateway.evaluator import evaluate_response

NO_PROMPT_REASON = "judge evaluators need the request prompt: send prompt"


class EvaluateRequest(BaseModel):
    contract: str
    output: str | dict
    prompt: str | None = None


def output_text(output: str | dict) -> str:
    """A string as-is; an object as JSON text so `field:` evaluators read its keys."""
    if isinstance(output, str):
        return output
    return json.dumps(output, ensure_ascii=False)


async def evaluate_output(
    req: EvaluateRequest,
    registry: Any,
    evaluator_specs: Callable[[Any], list],
    build_evaluators: Callable[[list, str | None, str | None], tuple[dict, list[dict]]],
) -> Any:
    if registry is None:
        raise HTTPException(status_code=503, detail="Contract registry not initialized")

    contract = registry.get(req.contract)
    if contract is None:
        raise HTTPException(status_code=404, detail=f"Contract '{req.contract}' not found")

    from server.gateway.tracing import get_tracer, start_span

    request_id = str(uuid.uuid4())
    with start_span(
        get_tracer(),
        "eva.contract.evaluate",
        {"contract": req.contract, "request_id": request_id},
    ) as span_ctx:
        trace_id = span_ctx.trace_id
        evaluator_map, skipped = build_evaluators(
            evaluator_specs(contract),
            req.prompt,
            None if req.prompt is not None else NO_PROMPT_REASON,
        )
        result = await evaluate_response(
            response_text=output_text(req.output),
            contract=contract,
            context={"request_id": request_id, "trace_id": trace_id},
            evaluator_map=evaluator_map,
        )

    content: dict = {"eva_status": "pass" if result.passed else "contract_violation"}
    if not result.passed:
        content["violations"] = result.violations
    if skipped:
        content["skipped"] = skipped
    content["request_id"] = request_id
    content["trace_id"] = trace_id
    return JSONResponse(status_code=200 if result.passed else 422, content=content)
