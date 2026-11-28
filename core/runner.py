# core/runner.py
import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

import pluggy

from core.categories import CaseOutcome, case_labels, category_scores
from core.chat_targets import ChatResult, TargetError
from core.adapters import CaseResultStore
from core.case_results import build_record
from core.dataset import Dataset, case_hash
from core.events import EventSink, NullEventSink
from core.models import (
    Artifact, EvaluatorResult, Invocation, Result, Run, Score, UsageRecord,
)

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
        # May return plain text, or a ChatResult carrying reasoning, model,
        # usage and latency (chat targets). Raising TargetError records the
        # case as an upstream_error instead of aborting the run.
        call_agent: Callable[[str, str], Awaitable[str | ChatResult]],
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

    async def execute(
        self, dataset: Dataset, on_test_done: Callable[[], None] | None = None
    ) -> Run:
        started_at = datetime.now(timezone.utc)
        run_id = str(uuid.uuid4())[:8]
        results: list[Result] = []
        outcomes: dict[int, CaseOutcome] = {}

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

                t0 = datetime.now(timezone.utc)
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
                    "metadata": test.metadata,
                }
                self.pm.hook.before_eval(test_id=test.id, context=run_ctx)
                chat: ChatResult | None = None
                target_error: str | None = None
                try:
                    if test.tools:
                        raw_response = await self.call_agent(
                            test.input, dataset.target,
                            tools=test.tools, tool_choice=test.tool_choice,
                        )
                    else:
                        raw_response = await self.call_agent(
                            test.input, dataset.target
                        )
                except TargetError as e:
                    raw_response, target_error = "", str(e)
                if isinstance(raw_response, ChatResult):
                    chat = raw_response
                    response = chat.text
                else:
                    response = raw_response
                if chat is not None:
                    # One request, log what came back: calls are recorded in
                    # reply order; nothing is executed.
                    for idx, call in enumerate(chat.tool_calls):
                        invocation_sink.emit_tool_call(
                            call.name,
                            call.args,
                            step_index=idx,
                            raw_args=call.raw_args,
                        )
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

                for cfg_dict, instance in ([] if target_error else builtin_specs):
                    evaluate = getattr(instance, "evaluate", None)
                    run_case = getattr(instance, "run_case", None)
                    if callable(run_case):
                        # Per-case evaluators (code_tests, exact_match, …)
                        # read test-case fields such as tests/expected_output.
                        score = await asyncio.to_thread(
                            run_case, response, test.model_dump()
                        )
                    elif callable(evaluate) and asyncio.iscoroutinefunction(evaluate):
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
                    if score is None:
                        continue  # evaluator not applicable to this case
                    paired.append((cfg_dict, score))

                if target_error:
                    paired.append((
                        {"name": "target", "mode": "binary"},
                        Score(value=0.0, reason=f"target error: {target_error}"),
                    ))
                    plugin_scores: list[Score] = []
                else:
                    plugin_scores = self.pm.hook.run_eval(
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

                if not paired:
                    run_skipped.append(f"{test.id}: no evaluator applied to this case")

                t1 = datetime.now(timezone.utc)
                duration_ms = int((t1 - t0).total_seconds() * 1000)

                test_results: list[Result] = []
                ev_results: list[EvaluatorResult] = []
                passed_all = True
                category, added = case_labels(test.metadata)

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

                outcomes[id(test)] = CaseOutcome(
                    test_id=test.id,
                    category=category,
                    added=added,
                    scored=bool(paired),
                    passed=bool(paired) and passed_all,
                )

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
                        status=(
                            "upstream_error" if target_error
                            else "pass" if passed_all else "fail"
                        ),
                        request_artifact_id=req_artifact_id,
                        response_artifact_id=resp_artifact_id,
                        provider=chat.provider if chat else None,
                        model=chat.model if chat else None,
                    )
                    artifacts = [req_artifact, resp_artifact]
                    meta: dict[str, Any] = {}
                    if category is not None:
                        meta["category"] = category
                    if added is not None:
                        meta["added"] = added
                    if target_error:
                        meta["error"] = target_error
                    if chat is not None:
                        meta["finish_reason"] = chat.finish_reason
                        meta["latency_ms"] = chat.latency_ms
                        if chat.reasoning:
                            reasoning_id = str(uuid.uuid4())
                            artifacts.append(Artifact(
                                artifact_id=reasoning_id,
                                kind="reasoning",
                                content_type="text/plain",
                                storage_backend="inline",
                                text_content=chat.reasoning,
                                size_bytes=len(chat.reasoning.encode()),
                                created_at=t1,
                            ))
                            meta["reasoning_artifact_id"] = reasoning_id
                    if meta:
                        invocation.metadata_json = json.dumps(meta)
                    self.storage.save_invocation(invocation, ev_results, artifacts)
                    if chat is not None:
                        self.storage.save_usage_record(UsageRecord(
                            usage_id=str(uuid.uuid4()),
                            invocation_id=invocation_id,
                            scope="agent",
                            provider=chat.provider,
                            model=chat.model or "unknown",
                            prompt_tokens=chat.usage.get("prompt_tokens"),
                            completion_tokens=chat.usage.get("completion_tokens"),
                            total_tokens=chat.usage.get("total_tokens"),
                            latency_ms=chat.latency_ms,
                            raw_usage_json=json.dumps(chat.usage),
                        ))
                    # Drain the per-invocation sink and persist ToolCall rows
                    # linked to this invocation. Drain isolation is guaranteed
                    # because each task owns its own sink instance.
                    tool_events = invocation_sink.drain()
                    if tool_events:
                        self.storage.save_tool_calls(invocation_id, tool_events)

                # --- per-case results: first result stands, upstream
                # errors and cases no evaluator applied to are not recorded.
                if isinstance(self.storage, CaseResultStore) and not target_error:
                    case_rec = build_record(
                        dataset=dataset.name,
                        target_id=dataset.result_target_id,
                        case=test.id,
                        case_hash_hex=case_hash(test),
                        results=test_results,
                        run_id=run_id,
                        at=started_at.isoformat(),
                        provider=chat.provider if chat else None,
                        model=chat.model if chat else None,
                    )
                    if case_rec is not None:
                        self.storage.put_case_results([case_rec])

                if on_test_done is not None:
                    on_test_done()
                return test_results

        if is_sequential:
            for t in dataset.scored_tests():
                batch = await run_one(t)
                results.extend(batch)
        else:
            all_results = await asyncio.gather(*[run_one(t) for t in dataset.scored_tests()])
            for batch in all_results:
                results.extend(batch)

        t_end = datetime.now(timezone.utc)
        passed = all(r.passed for r in results) if results else True
        cases = [outcomes[id(t)] for t in dataset.scored_tests()]
        return Run(
            run_id=run_id,
            dataset=dataset.name,
            target=dataset.target,
            results=results,
            started_at=started_at,
            duration_ms=int((t_end - started_at).total_seconds() * 1000),
            passed=passed,
            skipped=run_skipped,
            cases=cases,
            categories=category_scores(cases),
        )
