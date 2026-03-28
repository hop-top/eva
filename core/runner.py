# core/runner.py
import asyncio
import json
import uuid
from datetime import datetime
from typing import Any, Callable, Awaitable

import pluggy

from core.dataset import Dataset
from core.events import EventSink, NullEventSink
from core.costing import estimate_cost
from core.llm import LLMCompletion
from core.models import Artifact, EvaluatorResult, Invocation, Result, Run, Score, UsageRecord

try:
    from core.otel import NoopOtelAdapter
except ImportError:
    NoopOtelAdapter = None


def _make_noop_adapter():
    """Minimal no-op otel adapter when core.otel is absent."""

    class _NoopSpan:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def set_attribute(self, key: str, value: Any):
            pass

    class _Noop:
        def start_span(self, name: str, **attrs: Any):
            return _NoopSpan()

    return _Noop()


class Runner:
    def __init__(
        self,
        pm: pluggy.PluginManager,
        call_agent: Callable[[str, str], Awaitable[str]],
        # concurrency accepts str mode or legacy int (backwards compat)
        concurrency: int | str = "semaphore",
        max_workers: int = 4,
        min_score: float = 0.0,
        otel_adapter: Any = None,
        storage: Any = None,
        event_sink: EventSink | NullEventSink | None = None,
    ):
        self.pm = pm
        self.call_agent = call_agent
        self.min_score = min_score
        self.storage = storage  # optional SqliteStorage; None = no persistence
        # event_sink collects ToolCallEvents during a run; drained+persisted on
        # completion.  Defaults to NullEventSink so existing callers are unaffected.
        self.event_sink: EventSink | NullEventSink = event_sink or NullEventSink()

        # Backwards compat: old callers passed concurrency as plain int
        if isinstance(concurrency, int):
            self.concurrency_mode = "semaphore"
            self.max_workers = concurrency
        else:
            self.concurrency_mode = concurrency
            self.max_workers = max_workers

        if otel_adapter is not None:
            self.otel = otel_adapter
        elif NoopOtelAdapter is not None:
            self.otel = NoopOtelAdapter()
        else:
            self.otel = _make_noop_adapter()

    async def execute(self, dataset: Dataset) -> Run:
        started_at = datetime.utcnow()
        run_id = str(uuid.uuid4())[:8]
        results: list[Result] = []

        is_sequential = self.concurrency_mode == "sequential" or self.max_workers == 1
        worker_count = 1 if is_sequential else self.max_workers
        sem = asyncio.Semaphore(worker_count)

        async def run_one(test) -> list[Result]:
            async with sem:
                # --- observability: pre-call ids ---
                invocation_id = str(uuid.uuid4())
                req_artifact_id = str(uuid.uuid4())
                resp_artifact_id = str(uuid.uuid4())

                t0 = datetime.utcnow()
                # Provide event_sink so plugins/wrappers can emit tool events via:
                #   context["event_sink"].emit_tool_call(tool_name, args, ...)
                run_ctx: dict[str, Any] = {
                    "invocation_id": invocation_id,
                    "run_id": run_id,
                    "test_id": test.id,
                    "event_sink": self.event_sink,
                    "retrieval_context": test.retrieval_context,
                    "expected_output": test.expected_output,
                    "planned_steps": test.planned_steps,
                }
                self.pm.hook.before_eval(test_id=test.id, context=run_ctx)
                response = await self.call_agent(test.input, dataset.target)
                scores: list[Score] = self.pm.hook.run_eval(
                    response=response,
                    context={
                        "test": test.model_dump(),
                        **run_ctx,
                        "tool_events": run_ctx.get("tool_events", list(self.event_sink.events)),
                    },
                )
                t1 = datetime.utcnow()
                duration_ms = int((t1 - t0).total_seconds() * 1000)

                test_results: list[Result] = []
                ev_results: list[EvaluatorResult] = []
                passed_all = True

                for idx, score in enumerate(scores):
                    ev_configs = dataset.evaluators
                    ev_config = ev_configs[idx] if idx < len(ev_configs) else {}
                    if isinstance(ev_config, dict):
                        ev_name = ev_config.get("name", "unknown")
                        mode_val = ev_config.get("mode", "binary")
                        min_score = ev_config.get("min_score", self.min_score)
                    else:
                        ev_name = "unknown"
                        mode_val = "binary"
                        min_score = self.min_score

                    r = Result(
                        test_id=test.id,
                        evaluator=ev_name,
                        score=score,
                        mode=mode_val,
                        min_score=min_score,
                        duration_ms=duration_ms,
                    )
                    self.pm.hook.after_eval(test_id=test.id, score=score, context=run_ctx)
                    test_results.append(r)

                    if not r.passed:
                        passed_all = False

                    ev_results.append(EvaluatorResult(
                        evaluator_result_id=str(uuid.uuid4()),
                        invocation_id=invocation_id,
                        evaluator=ev_name,
                        mode=mode_val,
                        min_score=min_score,
                        score_value=score.value,
                        passed=r.passed,
                        reason=score.reason,
                        duration_ms=duration_ms,
                    ))

                # --- observability: persist if storage wired ---
                if self.storage is not None:
                    req_json = json.dumps({"input": test.input})
                    req_artifact = Artifact(
                        artifact_id=req_artifact_id,
                        kind="request",
                        content_type="application/json",
                        storage_backend="inline",
                        json_content=req_json,
                        size_bytes=len(req_json.encode()),
                        created_at=t0,
                    )
                    resp_artifact = Artifact(
                        artifact_id=resp_artifact_id,
                        kind="response",
                        content_type="text/plain",
                        storage_backend="inline",
                        text_content=response,
                        size_bytes=len(response.encode()),
                        created_at=t1,
                    )
                    invocation = Invocation(
                        invocation_id=invocation_id,
                        run_id=run_id,
                        source="offline_run",
                        dataset=dataset.name,
                        test_id=test.id,
                        target=dataset.target,
                        started_at=t0,
                        duration_ms=duration_ms,
                        status="pass" if passed_all else "fail",
                        request_artifact_id=req_artifact_id,
                        response_artifact_id=resp_artifact_id,
                    )
                    self.storage.save_invocation(
                        invocation, ev_results, [req_artifact, resp_artifact]
                    )
                    # Drain event sink and persist ToolCall rows linked to this invocation
                    tool_events = self.event_sink.drain()
                    if tool_events:
                        self.storage.save_tool_calls(invocation_id, tool_events)

                return test_results

        if is_sequential:
            for t in dataset.tests:
                batch = await run_one(t)
                results.extend(batch)
        else:
            all_results = await asyncio.gather(*[run_one(t) for t in dataset.tests])
            for batch in all_results:
                results.extend(batch)

        t_end = datetime.utcnow()
        passed = all(r.passed for r in results) if results else True
        return Run(
            run_id=run_id,
            dataset=dataset.name,
            target=dataset.target,
            results=results,
            started_at=started_at,
            duration_ms=int((t_end - started_at).total_seconds() * 1000),
            passed=passed,
        )
