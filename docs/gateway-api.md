# Gateway API Reference

Eva exposes a JSON HTTP API on the configured host/port (default `0.0.0.0:8080`).

---

## Authentication

All non-exempt endpoints require:

```
X-Eva-Key: <api-key>
```

Missing or invalid key → `401 {"detail": "Missing X-Eva-Key header"}` /
`401 {"detail": "Invalid API key"}`.

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
