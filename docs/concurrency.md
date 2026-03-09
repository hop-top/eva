# Concurrency Modes Guide

Eva's runner supports concurrent test execution via asyncio + semaphore.
Control via `--concurrency N` flag on `eva run`.

---

## Modes

### Sequential (default)

`--concurrency 1` — tests run one at a time, in order.

```
eva run --dataset evals/suite.yaml --concurrency 1
```

When to use:
- Agent has strict rate limits.
- Debugging a flaky agent.
- Reproducible ordering needed for logs.

### Semaphore (bounded parallel)

`--concurrency N` where N > 1 — up to N tests run concurrently;
extras wait on the semaphore.

```
eva run --dataset evals/suite.yaml --concurrency 4
```

When to use:
- Large suites (100+ tests).
- Agent handles parallel requests.
- Reducing wall-clock time is priority.

### Unbounded parallel

`--concurrency 0` — **not supported**. Use a large number instead:

```
eva run --dataset evals/suite.yaml --concurrency 50
```

Caution: may saturate agent or hit upstream rate limits.

---

## How it works

Internally, `Runner` creates an `asyncio.Semaphore(concurrency)`.
Every test coroutine acquires the semaphore before calling the agent.
All tests are gathered via `asyncio.gather` — the semaphore bounds
active requests, not total coroutines.

```python
# pseudocode — see core/runner.py for exact implementation
semaphore = asyncio.Semaphore(concurrency)

async def run_one(test):
    async with semaphore:
        response = await call_agent(test.input, dataset.target)
        scores   = pm.hook.run_eval(response=response, ...)
        ...

await asyncio.gather(*[run_one(t) for t in dataset.tests])
```

---

## Performance guidelines

| Suite size | Recommended `--concurrency` | Notes                          |
|------------|-----------------------------|--------------------------------|
| < 20 tests | 1 (sequential)              | No measurable gain from parallelism. |
| 20–100     | 4–8                         | Good balance.                  |
| 100–500    | 10–20                       | Monitor agent error rate.      |
| 500+       | 20–50                       | Check agent/proxy rate limits. |

---

## CI recommendation

For CI pipelines where reproducibility matters, use `--no-tui --concurrency 1`:

```
eva run --dataset evals/suite.yaml --no-tui --concurrency 1
```

For speed in CI with a capable agent:

```
eva run --dataset evals/suite.yaml --no-tui --concurrency 8
```
