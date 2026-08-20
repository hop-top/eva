# core/runner.py
import asyncio
import json
import uuid
from datetime import datetime
from typing import Any, Callable, Awaitable

import pluggy

from core.dataset import Dataset
from core.events import EventSink, NullEventSink
from core.models import Artifact, EvaluatorResult, Invocation, Result, Run, Score

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
        llm_adapter: Any = None,
        use_builtins: bool = True,
    ):
        self.pm = pm
        self.call_agent = call_agent
        self.min_score = min_score
        # Optional LLM adapter for judge-based builtin evaluators (see
        # core.llm.build_llm_adapter). None = judge refs skip with a reason.
        self.llm_adapter = llm_adapter
        # Resolve dataset.evaluators entries against the builtin factory
        # registry (core/evaluators/builtin.py) in addition to pluggy hooks.
        self.use_builtins = use_builtins
        self.storage = storage  # optional SqliteStorage; None = no persistence
        # NOTE: a single shared sink across concurrent invocations leaks tool
        # events between in-flight tests and lets one drain() clear another
        # test's buffer. The runner now allocates a fresh EventSink per
        # invocation inside run_one(); this attribute is retained only for
        # backwards-compat callers that read it directly. It is NOT consulted
        # during per-test evaluation or persistence.
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

        # --- resolve builtin evaluators once per run ---
        # Entries in dataset.evaluators whose name matches a builtin factory
        # are instantiated here and scored directly, correctly paired with
        # their own config. Entries with no factory remain "plugin configs":
        # pluggy scores are paired against those (by Score.metadata
        # evaluator_id when present, else positionally among themselves) —
        # never against builtin configs, which is the old mislabeling bug.
        builtin_specs: list[tuple[dict, Any]] = []
        plugin_cfgs: list[dict] = []
        run_skipped: list[str] = []
        factories: dict[str, Any] = {}
        if self.use_builtins:
            from core.evaluators.builtin import BUILTIN_EVALUATOR_FACTORIES
            factories = BUILTIN_EVALUATOR_FACTORIES
        for cfg in dataset.evaluators:
            cfg_dict = cfg if isinstance(cfg, dict) else {}
            name = cfg_dict.get("name")
            factory = factories.get(name) if name else None
            if factory is None:
                plugin_cfgs.append(cfg_dict)
                continue
            try:
                instance = factory(cfg_dict, self.llm_adapter)
            except ValueError as e:
                # Judge-based factory without an adapter: per-evaluator skip,
                # never a whole-run failure.
                run_skipped.append(f"{name}: {e}")
                continue
            builtin_specs.append((cfg_dict, instance))

        is_sequential = self.concurrency_mode == "sequential" or self.max_workers == 1
        worker_count = 1 if is_sequential else self.max_workers
        sem = asyncio.Semaphore(worker_count)

        async def run_one(test) -> list[Result]:
            async with sem:
                # --- observability: pre-call ids ---
                invocation_id = str(uuid.uuid4())
                req_artifact_id = str(uuid.uuid4())
                resp_artifact_id = str(uuid.uuid4())

                # Per-invocation EventSink: prevents tool-event interleaving
                # and drain() races when multiple tests run concurrently under
                # asyncio.gather. Each test gets its own buffer; nothing is
                # shared across the task set.
                invocation_sink = EventSink()

                t0 = datetime.utcnow()
                # Provide the per-invocation sink so plugins/wrappers can emit
                # tool events via:
                #   context["event_sink"].emit_tool_call(tool_name, args, ...)
                run_ctx: dict[str, Any] = {
                    "invocation_id": invocation_id,
                    "run_id": run_id,
                    "test_id": test.id,
                    "event_sink": invocation_sink,
                    "retrieval_context": test.retrieval_context,
                    "expected_output": test.expected_output,
                    "planned_steps": test.planned_steps,
                }
                self.pm.hook.before_eval(test_id=test.id, context=run_ctx)
                response = await self.call_agent(test.input, dataset.target)
                eval_ctx = {
                    "test": test.model_dump(),
                    **run_ctx,
                    "tool_events": run_ctx.get(
                        "tool_events", list(invocation_sink.events)
                    ),
                }

                # (config, score) pairs — pairing is by construction for
                # builtins and by evaluator_id/position-among-plugin-configs
                # for pluggy scores (alignment fix).
                paired: list[tuple[dict, Score]] = []

                for cfg_dict, instance in builtin_specs:
                    evaluate = getattr(instance, "evaluate", None)
                    if callable(evaluate) and asyncio.iscoroutinefunction(evaluate):
                        judge_ctx = {
                            k: v
                            for k, v in eval_ctx.items()
                            if k not in ("test",)
                        }
                        score = await evaluate(
                            prompt=test.input, response=response, **judge_ctx
                        )
                    else:
                        score = instance.run(response)
                    paired.append((cfg_dict, score))

                plugin_scores: list[Score] = self.pm.hook.run_eval(
                    response=response,
                    context=eval_ctx,
                )
                cfg_by_name = {
                    c.get("name"): c for c in plugin_cfgs if c.get("name")
                }
                for idx, score in enumerate(plugin_scores):
                    meta_id = (score.metadata or {}).get("evaluator_id")
                    if meta_id and meta_id in cfg_by_name:
                        cfg = cfg_by_name[meta_id]
                    elif idx < len(plugin_cfgs):
                        cfg = plugin_cfgs[idx]
                    else:
                        cfg = {}
                    paired.append((cfg, score))

                t1 = datetime.utcnow()
                duration_ms = int((t1 - t0).total_seconds() * 1000)

                test_results: list[Result] = []
                ev_results: list[EvaluatorResult] = []
                passed_all = True

                for ev_config, score in paired:
                    ev_name = ev_config.get("name", "unknown")
                    mode_val = ev_config.get("mode", "binary")
                    min_score = ev_config.get("min_score", self.min_score)

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
                    # Drain the per-invocation sink and persist ToolCall rows
                    # linked to this invocation. Drain isolation is guaranteed
                    # because each task owns its own sink instance.
                    tool_events = invocation_sink.drain()
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
            skipped=run_skipped,
        )
