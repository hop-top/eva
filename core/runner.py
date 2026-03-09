# core/runner.py
import asyncio
import uuid
from datetime import datetime
from typing import Callable, Awaitable

import pluggy

from core.dataset import Dataset
from core.models import Result, Run, Score


class Runner:
    def __init__(
        self,
        pm: pluggy.PluginManager,
        call_agent: Callable[[str, str], Awaitable[str]],
        concurrency: int = 1,
    ):
        self.pm = pm
        self.call_agent = call_agent
        self.concurrency = concurrency

    async def execute(self, dataset: Dataset) -> Run:
        started_at = datetime.utcnow()
        run_id = str(uuid.uuid4())[:8]
        semaphore = asyncio.Semaphore(self.concurrency)
        results = []

        async def run_one(test) -> list[Result]:
            async with semaphore:
                t0 = datetime.utcnow()
                self.pm.hook.before_eval(test_id=test.id, context={})
                response = await self.call_agent(test.input, dataset.target)
                scores: list[Score] = self.pm.hook.run_eval(
                    response=response, context={"test": test.model_dump()}
                )
                t1 = datetime.utcnow()
                duration_ms = int((t1 - t0).total_seconds() * 1000)

                test_results = []
                for score in scores:
                    # In Phase 1, we default to binary/1.0. 
                    # Future: map score to the specific evaluator config in dataset
                    mode = "binary"
                    min_score = 1.0
                    r = Result(
                        test_id=test.id,
                        evaluator="unknown", # Phase 1 simplification
                        score=score,
                        mode=mode,
                        min_score=min_score,
                        duration_ms=duration_ms,
                    )
                    self.pm.hook.after_eval(
                        test_id=test.id, score=score, context={}
                    )
                    test_results.append(r)
                return test_results

        tasks = [run_one(t) for t in dataset.tests]
        all_results = await asyncio.gather(*tasks)
        for batch in all_results:
            results.extend(batch)

        t_end = datetime.utcnow()
        passed = all(r.passed for r in results)
        return Run(
            run_id=run_id,
            dataset=dataset.name,
            target=dataset.target,
            results=results,
            started_at=started_at,
            duration_ms=int((t_end - started_at).total_seconds() * 1000),
            passed=passed,
        )
