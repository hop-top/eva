# Eva Cheatsheet — Agent

Quick reference for autonomous agents, scripts, and LLMs consuming the CLI or REST API.
Scannable in 30 seconds.

---

## Prerequisites

```bash
eva serve --contracts-dir ./contracts    # gateway on :8080
curl http://localhost:8080/health        # → {"status":"ok"}
eva version                              # verify CLI
```

---

## Agent Loop Contract

```
1. Validate    →  eva contract validate <file>  / (offline — no server needed)
2. Serve       →  eva serve (gateway must be running for proxy/invoke flows)
3. Run eval    →  eva run --dataset <path> --target <url>  (offline batch eval)
4. Proxy       →  POST /v1/proxy  (live gate: forward + evaluate in one call)
5. Invoke      →  POST /v1/contract/invoke  (contract-bound single call)
6. Observe     →  eva runs list / eva invocations show / eva failures list
```

**DO:** gate on run exit code (0 = all pass, 1 = failures).
**DO:** use `/v1/proxy` for ad-hoc evaluation, `/v1/contract/invoke` for contract-bound calls.
**DON'T:** annotate invocations before confirming `invocation_id` exists.

---

## Offline Eval

```bash
eva run \
  --dataset evals/suite.yaml \
  --target http://agent:8000/chat \
  --concurrency 4 \
  --no-tui                         # CI: plain output, exit 0/1
```

Exit code: `0` all pass · `1` any failure

---

## REST: Proxy (ad-hoc evaluation)

```http
POST /v1/proxy
Content-Type: application/json

{
  "target": "http://agent:8000/chat",
  "body": {"input": "Refund order 123"},
  "evaluators": [
    {"name": "no_pii",   "mode": "binary", "min_score": 1.0},
    {"name": "contains", "mode": "binary", "config": {"substring": "refund"}}
  ],
  "max_retries": 2,
  "hint": "Response must not contain PII and must mention refund",
  "backoff_ms": 500
}
```

### Response — pass

```json
{
  "eva_status": "pass",
  "attempts": 1,
  "response": { ... }
}
```

### Response — violation (HTTP 422)

```json
{
  "eva_status": "violation",
  "attempts": 3,
  "violations": [
    {"evaluator": "no_pii", "score": 0.0, "reason": "email detected"}
  ],
  "request_id": "...",
  "trace_id": "..."
}
```

---

## REST: Contract Invoke (contract-bound call)

```http
POST /v1/contract/invoke
Content-Type: application/json

{
  "contract": "refund_policy",
  "body": {"order_id": "ORD-123"}
}
```

Contract must be loaded via `--contracts-dir` on `eva serve`.

### Response — request invalid (HTTP 400)

```json
{
  "eva_status": "request_invalid",
  "violations": [...],
  "contract": "refund_policy"
}
```

---

## Evaluator Reference

| Name | Type | Key config fields |
|------|------|-------------------|
| `contains` | deterministic | `substring` |
| `regex_match` | deterministic | `pattern` |
| `json_schema_valid` | deterministic | _(none — validates response is valid JSON)_ |
| `no_pii` | heuristic | _(none)_ |
| `llm_judge` | LLM | `model`, `prompt_template`, `threshold` |
| `relevance` | LLM | `model` |
| `hallucination` | LLM | `model` |
| `tone` | LLM | `model`, `expected_tone` |
| `task_completion` | LLM | `model` |
| `safety` | LLM | `model` |
| `tool_correctness` | LLM | `model` |

Modes: `binary` (score ≥ min_score → pass) · `graded` (score stored, no gate)

---

## CLI Observe (scripting)

```bash
# List runs — filter by dataset, target, status
eva runs list --dataset <name> --status fail --limit 20

# Inspect single run
eva runs show --run-id <id>

# Invocation detail (evaluator scores, tool calls, usage)
eva invocations show --id <invocation-id>

# Side-by-side run comparison
eva compare --left <run-id-baseline> --right <run-id-new>

# Failed evaluations
eva failures list --evaluator no_pii --model gpt-4o --limit 50

# Token + cost report
eva usage report --dataset <name>

# Drift across recent runs
eva drift report --dataset <name> --target <url> --window 10 --threshold 0.1
```

All commands accept `--db <path>` to override default `.eva/state.db`.

---

## Contract Diff (CI regression gate)

```bash
eva contract diff v1.yaml v2.yaml
# exit 0 → no regressions
# exit 1 → regressions detected
```

Use in CI before deploying updated contracts.

---

## Annotation (post-eval labelling)

```bash
# Add human label to an invocation
eva annotate add \
  --invocation <id> \
  --label correct \
  --score 1.0 \
  --notes "verified manually" \
  --reviewer ci-bot

# List annotations
eva annotate list --invocation <id>

# Pending review queue
eva review queue --failed-only
```

---

## Error Handling

| Condition | Handling |
|-----------|----------|
| HTTP 422 from `/v1/proxy` | Violation — inspect `violations[]`; retry if `max_retries>0` used |
| HTTP 400 from `/v1/contract/invoke` | Request schema invalid — fix `body` fields |
| HTTP 404 from `/v1/contract/invoke` | Contract not loaded — check `--contracts-dir` |
| HTTP 503 from `/v1/contract/invoke` | Registry not initialized — ensure `eva serve` running |
| `eva run` exit 1 | ≥1 test failed — check output or `eva failures list` |
| Contract diff exit 1 | Regressions found — review `eva contract diff` output |

---

## Key Data Models

### ProxyRequest

| Field | Type | Notes |
|-------|------|-------|
| `target` | string | Upstream agent URL |
| `body` | object | Request body forwarded to agent |
| `evaluators` | EvaluatorSpec[] | Checks to run on response |
| `max_retries` | int | Retry on violation (default 0) |
| `hint` | string | Injected into retry prompt |
| `backoff_ms` | int | Delay between retries |

### EvaluatorSpec

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | Evaluator identifier |
| `mode` | string | `binary` \| `graded` |
| `min_score` | float | Pass threshold (default 1.0) |
| `config` | object | Evaluator-specific settings |

### Invocation (stored)

| Field | Notes |
|-------|-------|
| `invocation_id` | Stable UUID |
| `run_id` | Parent run (offline eval) or null (gateway) |
| `source` | `gateway_proxy` \| `offline_run` |
| `target` | Upstream URL |
| `contract_name` | Bound contract or null |
| `status` | `pass` \| `fail` \| `upstream_error` \| `request_invalid` |
| `model` | Model used by upstream |
| `duration_ms` | End-to-end latency |
| `request_artifact_id` | FK → request body artifact |
| `response_artifact_id` | FK → response artifact |
