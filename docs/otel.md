# OTEL Setup Guide

Eva emits OpenTelemetry spans throughout the eval lifecycle.
Two built-in adapters: `StdoutOtelAdapter` (default) and `NoopOtelAdapter`.

---

## Default: StdoutOtelAdapter

Prints JSON span data to stdout. Zero infra required.

Example output (one span per evaluator call):

```json
{
  "name": "eva.run_eval",
  "trace_id": "a1b2c3d4",
  "span_id": "e5f6g7h8",
  "start_time": "2025-03-01T10:00:00.123Z",
  "end_time":   "2025-03-01T10:00:00.456Z",
  "attributes": {
    "test_id":   "t1",
    "evaluator": "contains",
    "score":     1.0,
    "passed":    true
  }
}
```

No config needed — active by default in Phase 1.

---

## NoopOtelAdapter

Suppresses all OTEL output. Use in CI or where traces are unwanted.

```
EVA_OTEL=noop
```

*(env-var activation planned for Phase 2; adapter available in core now)*

---

## Sending to a backend (Phase 2+)

Eva will support OTLP export via the plugin system:

```
[project.entry-points."eva.otel"]
my_otel = "my_package:MyOtelPlugin"
```

Plugin receives span data; forwards to collector:

```python
# pseudocode
class MyOtelPlugin(EvaPlugin):
    def emit_span(self, span: dict) -> None:
        requests.post(COLLECTOR_URL, json=span)
```

---

## Span inventory

| Span name              | When emitted             | Key attributes                        |
|------------------------|--------------------------|---------------------------------------|
| `eva.run`              | Start/end of full run    | `run_id`, `dataset`, `target`         |
| `eva.run_one`          | Per test case            | `test_id`, `duration_ms`              |
| `eva.call_agent`       | HTTP call to agent       | `test_id`, `target_url`               |
| `eva.run_eval`         | Per evaluator invocation | `test_id`, `evaluator`, `score`       |
| `eva.after_eval`       | Post-eval hook           | `test_id`, `passed`                   |

---

## eva.yaml config (Phase 2)

```yaml
# planned — not yet active
otel:
  adapter: stdout   # stdout | noop | otlp
  endpoint: http://otel-collector:4318/v1/traces  # for otlp
  headers:
    Authorization: Bearer TOKEN
```

---

## Connecting to Jaeger (dev)

Quick local tracing stack:

```bash
# pseudocode — run in terminal
docker run -p 16686:16686 -p 4318:4318 jaegertracing/all-in-one

# then set in .env (Phase 2):
EVA_OTEL=otlp
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

Open `http://localhost:16686` to view traces.
