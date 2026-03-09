# core/runner.py
import asyncio
import uuid
from datetime import datetime
from typing import Any, Callable, Awaitable

import pluggy

from core.dataset import Dataset
from core.models import Result, Run, Score

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
    ):
        self.pm = pm
        self.call_agent = call_agent
        self.min_score = min_score

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
                t0 = datetime.utcnow()
                self.pm.hook.before_eval(test_id=test.id, context={})
                response = await self.call_agent(test.input, dataset.target)
                scores: list[Score] = self.pm.hook.run_eval(
                    response=response, context={"test": test.model_dump()}
                )
                t1 = datetime.utcnow()
                duration_ms = int((t1 - t0).total_seconds() * 1000)

                test_results = []
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
                    self.pm.hook.after_eval(test_id=test.id, score=score, context={})
                    test_results.append(r)
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
