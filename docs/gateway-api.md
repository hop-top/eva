# Gateway API Reference

Eva exposes a JSON HTTP API on the configured host/port (default `0.0.0.0:8080`).

---

## Authentication

All non-exempt endpoints require:

```
X-Eva-Key: <api-key>
```

Missing or invalid key → `401` with the structured error shown under
[Calling `POST /v1/contract/invoke`](#calling-post-v1contractinvoke).

Keys are looked up in the key store configured by `EVA_REDIS_URL` (see
[Security](security.md)). `eva serve` refuses to start without a key store
unless `--no-auth` is passed; with `--no-auth` no endpoint requires a key and
the header is ignored.

**Exempt paths** (no auth required):

- `GET /health`
- `GET /.well-known/agent.json`
- `GET /docs`
- `GET /openapi.json`
- `GET /redoc`

---

## Error Response Shape

Contract violations:

```
{
  "eva_status": "contract_violation",
  "attempts": <int>,
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

Generic errors (FastAPI / upstream):

```
{"detail": "<message>"}
```

---

## Endpoints

### `POST /v1/proxy`

Proxy a request to an arbitrary agent URL and evaluate the response inline.

#### Request

```
Content-Type: application/json
X-Eva-Key: <key>

{
  "target":      "<url>",
  "body":        {},
  "evaluators":  [
    {
      "name":      "<evaluator-name>",
      "mode":      "binary|threshold|warn",
      "min_score": 1.0,
      "config":    {}
    }
  ],
  "max_retries": 0,
  "hint":        "<string|null>",
  "backoff_ms":  0,
  "prompt_field": "<string|null>"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `target` | str | yes | — | Agent URL to forward to |
| `body` | object | no | `{}` | Request body forwarded to agent |
| `evaluators` | array | no | `[]` | Inline evaluator specs |
| `max_retries` | int | no | `0` | Retry attempts on violation |
| `hint` | str | no | `null` | Injected as `_eva_hint` on retries |
| `backoff_ms` | int | no | `0` | Sleep between retries (ms) |
| `prompt_field` | str | no | `null` | Top-level key of `body` holding the prompt for judge evaluators |

**Evaluator `name` values (built-in):** `contains`, `regex`, `json_schema_valid`, `no_pii`.
LLM-judge evaluators (for example `relevance`) also work when a judge is
configured; see [Judge evaluators in the gateway](llm-evaluators.md#judge-evaluators-in-the-gateway).

#### Response — pass (`200`)

```json
{
  "eva_status": "pass",
  "attempts": 1,
  "response": <agent-response-body>,
  "request_id": "<uuid>",
  "trace_id": "<string|null>"
}
```

#### Response — violation (`422`)

See [Error Response Shape](#error-response-shape) above.

#### Response — invalid inline evaluator (`422`)

An inline evaluator with invalid configuration is rejected before the agent is
called, with the problem in `detail`:

```json
{"detail": "evaluator 'regex': invalid regular expression '(': missing ), unterminated subpattern"}
```

A judge evaluator with no judge configured is not rejected; it is listed under
`skipped`.

#### Response — upstream error (`502`)

```json
{"detail": "<upstream error message>"}
```

---

### `POST /v1/contract/invoke`

Validate request, forward to agent, evaluate response — all per a named contract.

#### Request

```
Content-Type: application/json
X-Eva-Key: <key>

{
  "contract": "<contract-name>",
  "body":     {}
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `contract` | str | yes | Contract name as defined in YAML `name:` field |
| `body` | object | no | Request body forwarded to agent |

#### Response — pass (`200`)

```json
{
  "eva_status": "pass",
  "attempts": 1,
  "response": <agent-response-body>,
  "request_id": "<uuid>",
  "trace_id": "<string|null>"
}
```

#### Response — request invalid (`400`)

```json
{
  "eva_status": "request_invalid",
  "violations": [...],
  "contract": "<name>"
}
```

#### Response — contract not found (`404`)

```json
{"detail": "Contract '<name>' not found"}
```

#### Response — registry not initialised (`503`)

```json
{"detail": "Contract registry not initialized"}
```

---

### Calling `POST /v1/contract/invoke`

The caller-side view of the endpoint above: what to send and which response
to expect for each outcome. Send the contract name and the request to forward
as `body`; the gateway posts it to the contract's `provider` URL and evaluates
the reply. Every response is JSON.

```sh
curl -sS -X POST http://localhost:8080/v1/contract/invoke \
  -H "Content-Type: application/json" \
  -H "X-Eva-Key: eva_test_key" \
  -d '{"contract": "echo_policy", "body": {"message": "hi"}}'
```

| Status | `eva_status` | Meaning |
|--------|--------------|---------|
| `200` | `pass` | Request valid, agent answered, all evaluators passed |
| `422` | `contract_violation` | Evaluators failed after retries |
| `400` | `request_invalid` | `body` does not match the contract's `request_schema` |
| `401` | `unauthorized` | `X-Eva-Key` missing or not a known key |
| `404` | — | No contract with that name |
| `503` | — | Contract registry not initialised |

#### `200` — pass

```json
{
  "eva_status": "pass",
  "attempts": 1,
  "response": {"reply": "hello world"},
  "request_id": "<uuid>",
  "trace_id": null
}
```

`response` is the agent's response, parsed as JSON when it is JSON and
returned as a string otherwise. `trace_id` is `null` when tracing is off.

#### `422` — contract violation

```json
{
  "eva_status": "contract_violation",
  "attempts": 3,
  "violations": [
    {
      "evaluator": "contains",
      "score": 0.0,
      "reason": "Response does not contain 'NOPE'"
    }
  ],
  "request_id": "<uuid>",
  "trace_id": null
}
```

`violations` has one entry per failed evaluator; `reason` may be `null`.

#### Skipped evaluators

Judge evaluators that cannot run on a request are skipped (see
[Judge evaluators in the gateway](llm-evaluators.md#judge-evaluators-in-the-gateway)).
When at least one was skipped, both the `200` and the `422` body carry a
`skipped` list; when nothing was skipped the key is absent, so responses for
contracts without judge evaluators are unchanged.

```json
{
  "eva_status": "pass",
  "attempts": 1,
  "response": {"reply": "hello world"},
  "skipped": [
    {"evaluator": "relevance", "reason": "request body has no field 'question'"}
  ],
  "request_id": "<uuid>",
  "trace_id": null
}
```

A `422` body has the same `skipped` entry next to `violations`. The reasons are:
`no judge model configured`; `needs <inputs>, which the gateway cannot supply
(use dataset mode)`; `judge evaluators need the request prompt: set prompt_field`;
`request body has no field '<name>'`; `request body field '<name>' is not a string`.
The `400`, `404` and `503` bodies never carry `skipped`.

A request whose JSON envelope is malformed (for example `contract` missing)
is also rejected with `422`, but in FastAPI's shape, with no `eva_status`:

```json
{"detail": [{"type": "missing", "loc": ["body", "contract"], "msg": "Field required", "input": {"body": {}}}]}
```

#### `400` — request invalid

```json
{
  "eva_status": "request_invalid",
  "violations": [
    {"field": "$root", "message": "'message' is a required property"}
  ],
  "contract": "echo_policy"
}
```

The agent is not called.

#### `401` — missing or invalid key

```json
{
  "detail": "Missing X-Eva-Key header",
  "eva_status": "unauthorized",
  "violations": [
    {"field": "X-Eva-Key", "message": "Missing X-Eva-Key header"}
  ]
}
```

An unknown key returns the same shape with `"Invalid API key"` in `detail`
and in the violation's `message`. The agent is not called.

#### `404` — unknown contract

```json
{"detail": "Contract 'nope' not found"}
```

#### `503` — registry not initialised

```json
{"detail": "Contract registry not initialized"}
```

A contract file with an invalid evaluator configuration is skipped at load with
a warning naming the file and the problem, so it is `404` here, like any contract
that is not loaded.

`eva serve` always initialises the registry (empty when no contracts load, so
an unknown name is `404`); `503` arises only when the app is created without
one.

#### Stability

The command-result shape (`exit_code`, `stdout`, `stderr`; see
[Contracts for CLI output](contract-yaml-reference.md#contracts-for-cli-output))
and the `exit_code` alias for the `status_code` evaluator
([reference](evaluators-reference.md#status_code--exit_code)) are stable for
callers. Both are used by `eva run --contract` on a saved result and by
[`POST /v1/contract/evaluate`](#post-v1contractevaluate).

---

### `POST /v1/contract/evaluate`

Score output you already hold (captured CLI output, an exec step result)
against a named contract. Use `POST /v1/contract/invoke` when the gateway
should call the contract's provider; use this route when there is nothing to
call. It is the HTTP twin of `eva run --contract <file> --input <file>`. The
contract's evaluators, `mode` and `min_score` apply exactly as on invoke. No
provider is called, there is no retry, `request_schema` is not checked, and
nothing is persisted. The contract's `provider` is never contacted, so it may
be unreachable.

```sh
curl -sS -X POST http://localhost:8080/v1/contract/evaluate \
  -H "Content-Type: application/json" \
  -H "X-Eva-Key: eva_test_key" \
  -d '{"contract": "scan", "output": {"exit_code": 0, "stdout": "all good\n", "stderr": ""}}'
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `contract` | str | yes | Contract name as defined in YAML `name:` field |
| `output` | str or object | yes | The output to evaluate |
| `prompt` | str | no | The prompt the output answers; judge evaluators score it against `output`. An empty string is rejected |

`output` as a string is evaluated as-is. `output` as an object is serialised
to JSON text before evaluation, so an evaluator with `field: stdout` reads the
object's top-level `stdout` key. Arrays, numbers, booleans and `null` are
rejected. A string `output` is not parsed: a `field:`-scoped evaluator on a
plain string fails with `invalid JSON payload`. Unknown extra keys are ignored.

The key header is `X-Eva-Key`, as on every `/v1` route.

| Status | `eva_status` | Meaning |
|--------|--------------|---------|
| `200` | `pass` | All evaluators passed |
| `422` | `contract_violation` | At least one evaluator failed |
| `401` | `unauthorized` | `X-Eva-Key` missing or not a known key |
| `404` | — | No contract with that name |
| `503` | — | Contract registry not initialised |
| `422` | — | Malformed request (FastAPI shape) |

#### `200` — pass

```json
{
  "eva_status": "pass",
  "request_id": "<uuid>",
  "trace_id": null
}
```

There is no `attempts` and no `response` key: nothing was called.

#### `422` — contract violation

```json
{
  "eva_status": "contract_violation",
  "violations": [
    {
      "evaluator": "contains",
      "score": 0.0,
      "reason": "Response does not contain 'all good'"
    }
  ],
  "request_id": "<uuid>",
  "trace_id": null
}
```

#### Judge evaluators and `prompt`

Judge evaluators run when a judge is configured and `prompt` is sent; the
judge scores `prompt` against `output`. Without `prompt` they are skipped, and
the `200` or `422` body gains a `skipped` list (absent when nothing was
skipped):

```json
{
  "eva_status": "pass",
  "skipped": [
    {"evaluator": "relevance", "reason": "judge evaluators need the request prompt: send prompt"}
  ],
  "request_id": "<uuid>",
  "trace_id": null
}
```

Other skip reasons are `no judge model configured` and the
`needs <inputs>, which the gateway cannot supply` reasons listed under
[Judge evaluators in the gateway](llm-evaluators.md#judge-evaluators-in-the-gateway).
A judge call that fails scores `0.0` with a reason starting `judge error:`; it
is a violation, never a `500`. The contract's `prompt_field` is not used here.

#### `401` — missing or invalid key

```json
{
  "detail": "Missing X-Eva-Key header",
  "eva_status": "unauthorized",
  "violations": [
    {"field": "X-Eva-Key", "message": "Missing X-Eva-Key header"}
  ]
}
```

An unknown key returns the same shape with `"Invalid API key"` in `detail`
and in the violation's `message`.

#### `404` — unknown contract

```json
{"detail": "Contract 'nope' not found"}
```

#### `503` — registry not initialised

```json
{"detail": "Contract registry not initialized"}
```

#### `422` — malformed request

A missing `contract` or `output`, or an `output` that is not a string or
object, is rejected in FastAPI's shape, with no `eva_status`:

```json
{"detail": [{"type": "missing", "loc": ["body", "output"], "msg": "Field required", "input": {"contract": "scan"}}]}
```

---

### `GET /health`

Liveness probe.

#### Response (`200`)

```json
{"status": "ok"}
```

No auth required. Always returns `200` while the process is alive.

---

### `GET /.well-known/agent.json`

**EE feature** — requires `eva-ee` + `eva-agntcy` plugin.

ACP-compliant agent manifest; describes Eva gateway capabilities for AGNTCY
discovery.

#### Response (`200`)

```json
{
  "schema_version": "1.0",
  "name": "eva-gateway",
  "version": "<semver>",
  "description": "<string>",
  "capabilities": ["contract-enforcement", "response-evaluation", ...],
  "endpoints": [
    {
      "name": "proxy",
      "method": "POST",
      "url": "<base-url>/v1/proxy",
      "description": "<string>",
      "content_type": "application/json"
    },
    ...
  ],
  "protocols": ["ACP/1.0"],
  "interoperability": {
    "oasf": true,
    "a2a": false,
    "mcp": false,
    "slim": false
  }
}
```

No auth required. Returns `404` if `eva-agntcy` plugin is not installed.

---

## HTTP Status Code Summary

| Code | Meaning |
|------|---------|
| `200` | Success |
| `400` | Request schema violation |
| `401` | Missing or invalid API key |
| `404` | Contract not found |
| `422` | Contract violation (evaluator failed after retries) |
| `502` | Upstream agent error |
| `503` | Registry not initialised |
