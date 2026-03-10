# server/gateway/routes.py — FastAPI router for /v1/proxy and /v1/contract/invoke
from __future__ import annotations
import json
import uuid
from typing import Any
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from core.evaluators.contains import ContainsEvaluator
from core.evaluators.regex_match import RegexEvaluator
from core.evaluators.json_schema_valid import JsonSchemaEvaluator
from core.evaluators.no_pii import NoPiiEvaluator
from core.models import Contract, RetryPolicy, EvaluatorRef
from server.gateway.proxy import forward_request, ProxyError
from server.gateway.evaluator import evaluate_response
from server.gateway.retry import retry_with_hint, RetryExhausted

router = APIRouter(prefix="/v1")

_registry = None


def set_registry(registry) -> None:
    global _registry
    _registry = registry


# Built-in evaluator constructors keyed by name
_BUILTIN_EVALUATOR_FACTORIES = {
    "contains": lambda cfg: ContainsEvaluator(
        substring=cfg.get("substring", ""),
        case_sensitive=cfg.get("case_sensitive", True),
    ),
    "regex": lambda cfg: RegexEvaluator(pattern=cfg.get("pattern", ".*")),
    "json_schema_valid": lambda cfg: JsonSchemaEvaluator(schema=cfg.get("schema", {})),
    "no_pii": lambda cfg: NoPiiEvaluator(),
}


class EvaluatorSpec(BaseModel):
    name: str
    mode: str = "binary"
    min_score: float = 1.0
    config: dict = Field(default_factory=dict)


class ProxyRequest(BaseModel):
    target: str
    body: dict = Field(default_factory=dict)
    evaluators: list[EvaluatorSpec] = Field(default_factory=list)
    max_retries: int = 0
    hint: str | None = None
    backoff_ms: int = 0


def _build_evaluator_map(specs: list[EvaluatorSpec]) -> dict:
    evaluator_map = {}
    for spec in specs:
        factory = _BUILTIN_EVALUATOR_FACTORIES.get(spec.name)
        if factory:
            evaluator_map[spec.name] = factory(spec.config)
    return evaluator_map


def _violation_response(
    eva_status: str,
    attempts: int,
    violations: list[dict],
    request_id: str,
    trace_id: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "eva_status": eva_status,
            "attempts": attempts,
            "violations": violations,
            "request_id": request_id,
            "trace_id": trace_id,
        },
    )


@router.post("/proxy")
async def proxy(req: ProxyRequest) -> Any:
    from server.gateway.tracing import get_tracer, start_span
    tracer = get_tracer()
    request_id = str(uuid.uuid4())

    with start_span(
        tracer, "eva.proxy.request", {"target": req.target, "request_id": request_id}
    ) as span_ctx:
        trace_id = span_ctx.trace_id
        context = {"request_id": request_id, "trace_id": trace_id}
        evaluator_map = _build_evaluator_map(req.evaluators)

        contract = Contract(
            name="inline",
            provider=req.target,
            request_schema={},
            evaluators=[
                EvaluatorRef(name=s.name, mode=s.mode, min_score=s.min_score)
                for s in req.evaluators
            ],
            retry_policy=RetryPolicy(
                max_retries=req.max_retries,
                hint=req.hint,
                backoff_ms=req.backoff_ms,
            ),
        )

        async def call_agent(body: dict) -> str:
            proxy_resp = await forward_request(target=req.target, body=body, headers={})
            return proxy_resp.text

        try:
            retry_result = await retry_with_hint(
                agent_fn=call_agent,
                initial_body=req.body,
                contract=contract,
                evaluator_map=evaluator_map,
                context=context,
            )
        except ProxyError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        except RetryExhausted as exc:
            return _violation_response(
                eva_status="contract_violation",
                attempts=exc.attempts,
                violations=exc.violations,
                request_id=request_id,
                trace_id=trace_id,
            )

        try:
            response_data = json.loads(retry_result.response_text)
        except (json.JSONDecodeError, ValueError):
            response_data = retry_result.response_text

        return {
            "eva_status": "pass",
            "attempts": retry_result.attempts,
            "response": response_data,
            "request_id": request_id,
            "trace_id": trace_id,
        }


class InvokeRequest(BaseModel):
    contract: str
    body: dict = Field(default_factory=dict)


@router.post("/contract/invoke")
async def contract_invoke(req: InvokeRequest) -> Any:
    if _registry is None:
        raise HTTPException(status_code=503, detail="Contract registry not initialized")

    contract = _registry.get(req.contract)
    if contract is None:
        raise HTTPException(status_code=404, detail=f"Contract '{req.contract}' not found")

    from server.gateway.validation import validate_request_body, RequestValidationError
    from server.gateway.tracing import get_tracer, start_span
    tracer = get_tracer()
    request_id = str(uuid.uuid4())

    try:
        validate_request_body(req.body, contract.request_schema)
    except RequestValidationError as exc:
        return JSONResponse(
            status_code=400,
            content={
                "eva_status": "request_invalid",
                "violations": exc.violations,
                "contract": req.contract,
            },
        )

    with start_span(
        tracer, "eva.contract.invoke", {"contract": req.contract, "request_id": request_id}
    ) as span_ctx:
        trace_id = span_ctx.trace_id
        context = {"request_id": request_id, "trace_id": trace_id}
        evaluator_map = _build_evaluator_map(
            [EvaluatorSpec(name=ref.name, mode=ref.mode, min_score=ref.min_score)
             for ref in contract.evaluators]
        )

        async def call_agent(body: dict) -> str:
            proxy_resp = await forward_request(
                target=contract.provider, body=body, headers={}
            )
            return proxy_resp.text

        try:
            retry_result = await retry_with_hint(
                agent_fn=call_agent,
                initial_body=req.body,
                contract=contract,
                evaluator_map=evaluator_map,
                context=context,
            )
        except ProxyError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        except RetryExhausted as exc:
            return _violation_response(
                eva_status="contract_violation",
                attempts=exc.attempts,
                violations=exc.violations,
                request_id=request_id,
                trace_id=trace_id,
            )

        try:
            response_data = json.loads(retry_result.response_text)
        except (json.JSONDecodeError, ValueError):
            response_data = retry_result.response_text

        return {
            "eva_status": "pass",
            "attempts": retry_result.attempts,
            "response": response_data,
            "request_id": request_id,
            "trace_id": trace_id,
        }
