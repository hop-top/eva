# server/gateway/routes.py — FastAPI router for /v1/proxy and /v1/contract/invoke
from __future__ import annotations
import json
import random
import uuid
from datetime import datetime
from typing import Any
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from core.evaluators.contains import ContainsEvaluator
from core.evaluators.regex_match import RegexEvaluator
from core.evaluators.json_schema_valid import JsonSchemaEvaluator
from core.evaluators.no_pii import NoPiiEvaluator
from core.costing import estimate_cost
from core.events import EventSink, NullEventSink
from core.models import (
    Artifact, Contract, EvaluatorResult, Invocation,
    RetryPolicy, EvaluatorRef, UsageRecord,
)
from server.gateway.proxy import forward_request, ProxyError
from server.gateway.evaluator import evaluate_response
from server.gateway.retry import retry_with_hint, RetryExhausted

def _capture_usage(
    response_data: Any,
    invocation_id: str,
    scope: str,
    target: str,
) -> None:
    """Extract usage from response_data (if present) and persist to _storage."""
    if _storage is None:
        return
    usage_dict: dict = {}
    if isinstance(response_data, dict):
        usage_dict = response_data.get("usage") or {}
    if not usage_dict:
        return
    provider = response_data.get("model", "").split("/")[0] if isinstance(response_data, dict) else ""
    model = response_data.get("model", target) if isinstance(response_data, dict) else target
    prompt_tokens = usage_dict.get("prompt_tokens")
    completion_tokens = usage_dict.get("completion_tokens")
    total_tokens = usage_dict.get("total_tokens")
    cost = estimate_cost(
        provider=provider,
        model=model,
        prompt_tokens=prompt_tokens or 0,
        completion_tokens=completion_tokens or 0,
    )
    usage_record = UsageRecord(
        usage_id=str(uuid.uuid4()),
        invocation_id=invocation_id,
        scope=scope,
        provider=provider or None,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=cost,
        raw_usage_json=json.dumps(usage_dict),
    )
    _storage.save_usage_record(usage_record)


router = APIRouter(prefix="/v1")

_registry = None
_storage = None
_sample_rate: float = 1.0  # fraction of requests for which artifact writes occur


def set_registry(registry) -> None:
    global _registry
    _registry = registry


def set_storage(storage) -> None:
    """Wire a SqliteStorage (or any compatible) instance for invocation persistence."""
    global _storage
    _storage = storage


def set_sample_rate(rate: float) -> None:
    """Set the observability sample rate (0.0-1.0). Called once at app startup."""
    global _sample_rate
    _sample_rate = max(0.0, min(1.0, rate))


def _is_sampled() -> bool:
    """Return True when this request should have full artifact writes."""
    return random.random() < _sample_rate


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


def _persist_invocation(
    *,
    started_at: datetime,
    ended_at: datetime,
    request_body: dict,
    response_text: str | None,
    target: str,
    contract_name: str,
    request_id: str,
    trace_id: str | None,
    status: str,
    eval_results: list | None = None,
    run_id: str | None = None,
    event_sink: EventSink | NullEventSink | None = None,
    sampled: bool = True,
) -> None:
    """Build Artifact + Invocation + EvaluatorResult rows and persist via _storage.

    No-op when _storage is None.

    When *sampled* is False the Invocation stub is still written (so counts remain
    accurate) but artifact writes and evaluator-result rows are skipped.

    Event contract for upstream agents:
      Upstream agents MUST emit tool calls via context["event_sink"].emit_tool_call(...)
      for every tool invocation they make.  Without emitted events, ToolCall rows will
      not be created and tool-level verification (audit, replay, drift) will be partial.
      The sink is provided in context["event_sink"]; it is always safe to call even
      when observability is disabled (NullEventSink is the default).
    """
    if _storage is None:
        return

    duration_ms = int((ended_at - started_at).total_seconds() * 1000)

    # --- artifact writes (skipped when not sampled) ---
    req_artifact_id: str | None = None
    resp_artifact_id: str | None = None
    artifacts: list[Artifact] = []

    if sampled:
        req_artifact_id = str(uuid.uuid4())
        req_json = json.dumps(request_body)
        artifacts.append(Artifact(
            artifact_id=req_artifact_id,
            kind="request",
            content_type="application/json",
            storage_backend="inline",
            json_content=req_json,
            size_bytes=len(req_json.encode()),
            created_at=started_at,
        ))

        if response_text is not None:
            resp_artifact_id = str(uuid.uuid4())
            artifacts.append(Artifact(
                artifact_id=resp_artifact_id,
                kind="response",
                content_type="text/plain",
                storage_backend="inline",
                text_content=response_text,
                size_bytes=len(response_text.encode()),
                created_at=ended_at,
            ))

    invocation_id = str(uuid.uuid4())
    invocation = Invocation(
        invocation_id=invocation_id,
        run_id=run_id,
        source="gateway_proxy",
        target=target,
        contract_name=contract_name,
        request_id=request_id,
        trace_id=trace_id,
        started_at=started_at,
        duration_ms=duration_ms,
        status=status,  # type: ignore[arg-type]
        request_artifact_id=req_artifact_id,
        response_artifact_id=resp_artifact_id,
    )

    ev_results: list[EvaluatorResult] = []
    if sampled:
        for r in (eval_results or []):
            ev_results.append(EvaluatorResult(
                evaluator_result_id=str(uuid.uuid4()),
                invocation_id=invocation_id,
                evaluator=r.evaluator,
                mode=r.mode,
                min_score=r.min_score,
                score_value=r.score.value,
                passed=r.passed,
                reason=r.score.reason,
                duration_ms=r.duration_ms,
            ))

    _storage.save_invocation(invocation, ev_results, artifacts)

    # Drain event sink and persist ToolCall rows linked to this invocation (pass + fail paths)
    if sampled and event_sink is not None:
        tool_events = event_sink.drain()
        if tool_events:
            _storage.save_tool_calls(invocation_id, tool_events)


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
        # event_sink injected so upstream agents can emit tool calls via
        #   context["event_sink"].emit_tool_call(tool_name, args, ...)
        sink = EventSink()
        context = {"request_id": request_id, "trace_id": trace_id, "event_sink": sink}
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

        sampled = _is_sampled()
        started_at = datetime.utcnow()
        retry_result = None
        exc_proxy: ProxyError | None = None
        exc_retry: RetryExhausted | None = None

        try:
            retry_result = await retry_with_hint(
                agent_fn=call_agent,
                initial_body=req.body,
                contract=contract,
                evaluator_map=evaluator_map,
                context=context,
            )
        except ProxyError as exc:
            exc_proxy = exc
        except RetryExhausted as exc:
            exc_retry = exc
        finally:
            ended_at = datetime.utcnow()
            if exc_proxy is None:  # upstream_error path skips persistence (no response)
                _status = "pass" if retry_result is not None else "fail"
                _resp_text = (
                    retry_result.response_text if retry_result is not None
                    else (exc_retry.last_response if exc_retry else None)
                )
                _eval_results = (
                    retry_result.eval_result.results
                    if retry_result is not None and retry_result.eval_result
                    else []
                )
                _persist_invocation(
                    started_at=started_at,
                    ended_at=ended_at,
                    request_body=req.body,
                    response_text=_resp_text,
                    target=req.target,
                    contract_name="inline",
                    request_id=request_id,
                    trace_id=trace_id,
                    status=_status,
                    eval_results=_eval_results,
                    event_sink=sink,
                    sampled=sampled,
                )

        if exc_proxy is not None:
            raise HTTPException(status_code=502, detail=str(exc_proxy))
        if exc_retry is not None:
            return _violation_response(
                eva_status="contract_violation",
                attempts=exc_retry.attempts,
                violations=exc_retry.violations,
                request_id=request_id,
                trace_id=trace_id,
            )

        try:
            response_data = json.loads(retry_result.response_text)  # type: ignore[union-attr]
        except (json.JSONDecodeError, ValueError):
            response_data = retry_result.response_text  # type: ignore[union-attr]

        return {
            "eva_status": "pass",
            "attempts": retry_result.attempts,  # type: ignore[union-attr]
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
        # event_sink injected so upstream agents can emit tool calls via
        #   context["event_sink"].emit_tool_call(tool_name, args, ...)
        invoke_sink = EventSink()
        context = {"request_id": request_id, "trace_id": trace_id, "event_sink": invoke_sink}
        evaluator_map = _build_evaluator_map(
            [EvaluatorSpec(name=ref.name, mode=ref.mode, min_score=ref.min_score)
             for ref in contract.evaluators]
        )

        async def call_agent(body: dict) -> str:
            proxy_resp = await forward_request(
                target=contract.provider, body=body, headers={}
            )
            return proxy_resp.text

        invoke_sampled = _is_sampled()
        started_at = datetime.utcnow()
        retry_result = None
        exc_proxy: ProxyError | None = None
        exc_retry: RetryExhausted | None = None

        try:
            retry_result = await retry_with_hint(
                agent_fn=call_agent,
                initial_body=req.body,
                contract=contract,
                evaluator_map=evaluator_map,
                context=context,
            )
        except ProxyError as exc:
            exc_proxy = exc
        except RetryExhausted as exc:
            exc_retry = exc
        finally:
            ended_at = datetime.utcnow()
            if exc_proxy is None:
                _status = "pass" if retry_result is not None else "fail"
                _resp_text = (
                    retry_result.response_text if retry_result is not None
                    else (exc_retry.last_response if exc_retry else None)
                )
                _eval_results = (
                    retry_result.eval_result.results
                    if retry_result is not None and retry_result.eval_result
                    else []
                )
                _persist_invocation(
                    started_at=started_at,
                    ended_at=ended_at,
                    request_body=req.body,
                    response_text=_resp_text,
                    target=contract.provider,
                    contract_name=req.contract,
                    request_id=request_id,
                    trace_id=trace_id,
                    status=_status,
                    eval_results=_eval_results,
                    event_sink=invoke_sink,
                    sampled=invoke_sampled,
                )

        if exc_proxy is not None:
            raise HTTPException(status_code=502, detail=str(exc_proxy))
        if exc_retry is not None:
            return _violation_response(
                eva_status="contract_violation",
                attempts=exc_retry.attempts,
                violations=exc_retry.violations,
                request_id=request_id,
                trace_id=trace_id,
            )

        try:
            response_data = json.loads(retry_result.response_text)  # type: ignore[union-attr]
        except (json.JSONDecodeError, ValueError):
            response_data = retry_result.response_text  # type: ignore[union-attr]

        _capture_usage(response_data, request_id, "agent", contract.provider)
        return {
            "eva_status": "pass",
            "attempts": retry_result.attempts,  # type: ignore[union-attr]
            "response": response_data,
            "request_id": request_id,
            "trace_id": trace_id,
        }
