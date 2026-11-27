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
[Security](security.md)). API-key auth is applied when `EVA_REDIS_URL` is set;
what the gateway does when no key store is configured is not covered here.

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
  "backoff_ms":  0
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

**Evaluator `name` values (built-in):** `contains`, `regex`, `json_schema_valid`, `no_pii`.

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
to expect for each outcome. Send the contract name and the payload to check as
`body`. Every response is JSON.

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

`eva serve` always initialises the registry (empty when no contracts load, so
an unknown name is `404`); `503` arises only when the app is created without
one.

#### Stability

The exec-step result shape (`exit_code`, `stdout`, `stderr`; see
[Contracts for exec-step output](contract-yaml-reference.md#contracts-for-exec-step-output-tlc-flow-exec))
and the `exit_code` alias for the `status_code` evaluator
([reference](evaluators-reference.md#status_code--exit_code)) are stable for
callers. A caller that sends an exec step's output as `body` can rely on both.

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
