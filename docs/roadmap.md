# Eva Roadmap

## Scope

Three deliverables owned by the Eva team:

- **Eva Core** — the engine (`eva/core/`, `eva/cli/`)
- **Eva Server** — the gateway (`eva/server/`)
- **Eva Plugins** — official adapter/integration packages

---

## Phase 1 — Eva Core Foundation

**Goal:** Prove the central primitive. A developer can define a contract, run evals locally, and gate CI.

### Deliverables
- Contract model + YAML format (the central primitive — everything else depends on this)
- Evaluator interface + pluggy hook specs (`before_eval`, `run_eval`, `after_eval`)
- Built-in deterministic evaluators (Tier 1):
  - `json_schema_valid`, `contains`, `regex`, `latency`, `status_code`, `no_pii`
- Plugin system — local `eva_plugins.py` (conftest-style) + entry_points (package-style)
- SQLite storage adapter (default)
- `eva init` — scaffold `evals/`, `eva_plugins.py`, `.env`
- `eva run` — sequential execution, basic terminal output
- `eva contract validate` — validate a contract YAML file
- Exit codes for CI (`0` = pass, `1` = fail)

### Methodology
Doc-first → E2E tests (subprocess, assert stdout + exit code) → implementation

### Team
Team Core only.

### Gate to Phase 2
Contract model + evaluator interface locked. All teams align before proceeding.

---

## Phase 2 — Eva Core Power

**Goal:** Full eval capability. LLM judging, concurrency, observability, adapter interfaces ready for Team Plugins.

### Deliverables
- LiteLLM adapter — LLM-as-judge evaluators (Tier 2):
  - `relevance`, `hallucination`, `tone`, `task_completion`, `safety`
- Scoring modes per evaluator: `binary` / `threshold` / `warn`
- Concurrency modes: async concurrent (default), sequential, parallel workers
  - Config in `eva.yaml`, overridable per run via flags
- TUI — rich live progress, results table, evaluator scores
- Pluggable storage adapter interface — SQLite default, interface ready for `eva-postgres`
- Pluggable state adapter interface — Redis default
- OTEL tracing interface — stdout exporter default, interface ready for `eva-otlp`
  - Spans: request, evaluator, retry, result
- JSONL dataset support (alongside YAML)
- `eva contract diff` — detect contract regressions between two versions

### Team
Team Core. Team Plugins unblocked once adapter interfaces are stable.

### Gate to Phase 3
Adapter interfaces (storage, state, OTEL) locked. Eva Server + Team Plugins start.

---

## Phase 3 — Eva Server + Official Plugins v1

**Goal:** Production gateway operational. Official adapters published.

### Eva Server Deliverables
- `eva serve` — FastAPI gateway (sidecar + multi-agent modes)
- Contract registry — YAML → OASF, hot-reload, no restart needed
- Request validation — validate incoming request against `contract.request_schema` before forwarding
- Response evaluation — inline (sync) + ARQ (async/fire-and-forget)
- Retry + self-healing — hint injection, configurable `max_retries`
- Structured error response on contract violation (never silent failure)
- `POST /v1/proxy` — dumb proxy with response evaluation
- `POST /v1/contract/invoke` — contract-aware: validates request + evaluates response
- OTEL spans throughout request lifecycle

### Official Plugin Deliverables
- `eva-postgres` — Postgres storage adapter (via SQLModel/SQLAlchemy)
- `eva-otlp` — OTLP exporter (pipe traces to Jaeger, Datadog, Grafana Tempo, etc.)
- `eva-a2a` — A2A Agent Card import → Eva contract YAML
- `eva-mcp` — MCP server manifest → Eva contract YAML

### Teams
Team Server + Team Plugins in parallel.

### Gate to Phase 4
Gateway API stable. Ecosystem builders can depend on it.

---

## Phase 4 — Hardening + AGNTCY Alignment

**Goal:** Production-grade reliability. Full AGNTCY alignment.

### Eva Server Hardening
- Auth + rate limiting on gateway
- Webhook/event emission on contract violations
- Drift detection — regression scoring across runs over time

### Official Plugin Deliverables
- `eva-agntcy` — full AGNTCY/OASF alignment (ACP endpoint, OASF registry, SLIM messaging)

### Teams
All teams contributing.

> **Note:** Domain-specific evaluator packages (`eva-evaluators-finance`, `eva-evaluators-healthcare`, `eva-evaluators-legal`) are ecosystem deliverables — built by third parties on top of Eva's plugin interface. See `docs/ecosystem.md`.

---

## Team Structure

### Team Core
**Owns:** `eva/core/`, `eva/cli/`

Responsibilities:
- Contract model, evaluator interface, pluggy hook system
- Built-in evaluators (deterministic + LLM-judge)
- Adapter interfaces (storage, state, OTEL)
- CLI commands + TUI
- E2E test suite for CLI

Unblocked: from day one.

---

### Team Server
**Owns:** `eva/server/`

Responsibilities:
- FastAPI gateway
- Contract registry + OASF integration
- ARQ async queue
- Retry/self-healing middleware
- E2E test suite for API (`httpx` integration tests)

Unblocked: after Phase 1 gate (contract model stable).

---

### Team Plugins
**Owns:** official plugin packages (`eva-postgres`, `eva-otlp`, `eva-a2a`, `eva-mcp`, `eva-agntcy`, domain evaluators)

Responsibilities:
- Implement adapter interfaces defined by Team Core
- Maintain compatibility with Eva Core versions
- Publish to PyPI

Unblocked: after Phase 2 gate (adapter interfaces stable).

---

## Sync Points

| Point | When | What gets locked |
|---|---|---|
| Phase 1 gate | End of Phase 1 | Contract model + evaluator interface |
| Phase 2 gate | End of Phase 2 | Storage, state, OTEL adapter interfaces |
| Phase 3 gate | End of Phase 3 | Gateway API (v1 stable) |
