# Retry + Self-Healing Reference

Eva's retry engine re-calls the target agent on contract violations, injecting
correction hints into subsequent requests.

---

## How It Works

1. Eva calls the target agent with the request body.
2. Response passed through all configured evaluators.
3. If all evaluators pass → success; no retry.
4. If any evaluator fails:
   - If retries remain: inject `_eva_hint` into request body, wait `backoff_ms`,
     re-call agent.
   - If retries exhausted: raise `RetryExhausted`; return `422` to caller.

### Hint Injection

On retry attempts (attempt > 1), `contract.retry_policy.hint` is added to the
request body as `_eva_hint`:

```
body["_eva_hint"] = "<hint string>"
```

The agent receives the augmented body and is expected to use the hint to correct
its output. Hint injection is skipped on attempt 1 and when `hint` is `null`.

### Backoff

`backoff_ms` sleep between attempts (not exponential — fixed delay).
Set `backoff_ms: 0` for immediate retry.

---

## Contract YAML Configuration

```yaml
retry_policy:
  max_retries: 2          # number of retries (total attempts = max_retries + 1)
  hint: "Be concise."     # injected as _eva_hint on each retry
  backoff_ms: 500         # ms to sleep between attempts
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_retries` | int | `2` | Maximum retry count after first failure |
| `hint` | str\|null | `null` | Correction hint injected into retry body |
| `backoff_ms` | int | `0` | Fixed delay between attempts (ms) |

Total maximum attempts = `max_retries + 1`.

---

## On Exhaustion

When all attempts fail, Eva returns `HTTP 422`:

```json
{
  "eva_status": "contract_violation",
  "attempts": <total-attempts>,
  "violations": [
    {
      "evaluator": "<name>",
      "score": <float>,
      "reason": "<string|null>"
    }
  ],
  "request_id": "<uuid>",
  "trace_id": "<string|null>"
}
```

`violations` reflects the last attempt's failed evaluators.

---

## Interaction with Evaluators

Each attempt runs the full evaluator chain. Any evaluator failure triggers a
retry (if retries remain). The triggering evaluator appears in `violations`.

Evaluator modes affect pass/fail:

| Mode | Passes when |
|------|-------------|
| `binary` | `score == 1.0` |
| `threshold` | `score >= min_score` |
| `warn` | always (logged, never fails) |

`warn`-mode evaluators never trigger retries.

---

## Observability

OTEL spans emitted per attempt when tracing is configured:

| Span | Attributes |
|------|------------|
| `eva.proxy.request` | `target`, `request_id` |
| `eva.contract.invoke` | `contract`, `request_id` |

`attempt` number is included in the evaluation context passed to evaluators.
Individual per-evaluator spans: emitted by `eva.gateway.evaluator` internals
when OTEL provider is active (requires `eva-otlp` or compatible provider).

Install `eva-otlp` and call `OtlpExporter(endpoint=...).setup()` at startup
to export spans. See [OTEL guide](otel.md).

---

## Example

Contract with retry and hint:

```yaml
name: summariser.summarise
provider: http://localhost:9000/summarise
evaluators:
  - name: contains
    mode: binary
    min_score: 1.0
    config:
      substring: "Summary:"
      case_sensitive: false
retry_policy:
  max_retries: 2
  hint: "Always begin your response with 'Summary:'"
  backoff_ms: 200
```

On violation of `contains` evaluator:
- Attempt 2: body gains `_eva_hint: "Always begin your response with 'Summary:'"`.
- Attempt 3: same hint, another 200ms wait.
- Exhaustion: `422` with `violations: [{evaluator: "contains", score: 0.0, ...}]`.
