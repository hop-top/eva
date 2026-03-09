# Eva Architecture Design
*2026-03-09*

## What Eva Is

Eva is the enforcement layer for AI agent behavior. It operates at every stage of the software development lifecycle — on a developer's laptop, in CI/CD pipelines, and inside production systems — enforcing behavioral contracts between agents.

Every other evaluation tool works offline: you run tests, get a report, act on it manually. Eva also works inline. In production, it sits in the request path, evaluates responses, and retries when an agent fails. The QA loop becomes autonomous.

## The Four Personas

| Persona | How they use Eva |
|---|---|
| Developer | Runs `eva run` locally — like pytest for their agent |
| Team / CI | Gates pull requests — `eva run --ci` fails the build on contract violations |
| SaaS platform | Runs `eva serve` — gateway that intercepts live traffic and enforces contracts |
| Agent | Calls other agents through Eva — gets a guaranteed-valid response or a structured failure |

The last persona is the most important. Eva is agent-native and agent-first. Automating evaluation creates an infinite QA loop: agents invoke agents, Eva enforces the contracts, the system self-corrects without human intervention.

## Eva's Differentiator

DeepEval, Langfuse, Promptfoo, and Opik evaluate responses after the fact. None sit in the request path. None enforce contracts at runtime. None self-heal.

Eva does all three.

## The Three Deliverables

**Eva Core** — the engine. Ships as `eva`. Used by developers and CI.

**Eva Server** — the gateway. Ships as `eva-server`. Used by SaaS platforms and agents.

**Eva Plugins** — official adapters. Published separately on PyPI. Extend Core and Server without bloating either.

---

## Protocol Alignment

Eva adopts AGNTCY (OASF + ACP) as its native protocol. AGNTCY is the interoperability hub — aligning here gives Eva compatibility with Google's A2A and Anthropic's MCP through AGNTCY's own adapters.

Contracts live as human-readable YAML. Eva compiles them to OASF internally. Developers never touch OASF directly.

Adapters for agents not yet on AGNTCY:
- `eva-a2a` — imports A2A Agent Cards
- `eva-mcp` — imports MCP server manifests
- `eva-agntcy` — full OASF registry + ACP endpoint alignment

---

## Component Structure

```
eva/
├── cli/       # Typer CLI + TUI (rich)
├── core/      # Engine — evaluators, adapters, plugin system, models
└── server/    # FastAPI gateway, contract registry, ARQ queue
```

### Core Internals

```
core/
├── evaluators/   # Built-in: deterministic (Tier 1) + LLM-judge (Tier 2)
├── adapters/     # LLM (LiteLLM), Storage, State, OTEL — all pluggable
├── plugins/      # pluggy hook specs + loader
└── models/       # Pydantic: Score, Result, Contract, Run, RetryPolicy
```

### Server Internals

```
server/
├── gateway/      # Request interception, retry, self-healing
├── contracts/    # OASF contract registry, hot-reload
└── queue/        # ARQ workers for async jobs
```

---

## Data Model

```python
class Score(BaseModel):
    value: float          # always 0.0–1.0
    reason: str | None
    metadata: dict = {}

class Result(BaseModel):
    test_id: str
    evaluator: str
    score: Score
    mode: Literal["binary", "threshold", "warn"]
    min_score: float = 1.0
    passed: bool          # computed from mode + score
    duration_ms: int
    trace_id: str | None  # links to OTEL span

class Run(BaseModel):
    run_id: str
    dataset: str
    target: str
    results: list[Result]
    started_at: datetime
    duration_ms: int
    passed: bool

class Contract(BaseModel):
    name: str
    provider: str         # OASF agent identifier
    consumer: str | None
    request_schema: dict  # JSON Schema
    evaluators: list[EvaluatorRef]
    retry_policy: RetryPolicy

class RetryPolicy(BaseModel):
    max_retries: int = 2
    hint: str | None
    backoff_ms: int = 0
```

### Dataset Format

```yaml
# evals/refunds.yaml
name: refund_suite
target: http://localhost:8000/chat
evaluators:
  - name: corporate_compliance
    mode: binary
  - name: answer_quality
    mode: threshold
    min_score: 0.7
  - name: tone_check
    mode: warn
tests:
  - id: refund_01
    input: "Refund order 123"
  - id: refund_02
    input: "Give me 30% off"
```

---

## Evaluator System

### Tier 1 — Deterministic (zero LLM cost)
`json_schema_valid`, `contains`, `regex`, `latency`, `status_code`, `no_pii`

### Tier 2 — LLM-as-Judge (via LiteLLM)
`relevance`, `hallucination`, `tone`, `task_completion`, `safety`

Best practices applied: binary/low-precision scoring, chain-of-thought in judge prompts, low temperature, structured JSON output, separate evaluator per criterion.

### Tier 3 — Custom Plugins

**Local dev** (drop-in, like pytest's conftest.py):
```python
# eva_plugins.py
from eva.core import evaluator, Score

@evaluator(name="corporate_compliance", mode="binary")
def check_compliance(response: str, context: dict) -> Score:
    if "30% off" in response:
        return Score(value=0.0, reason="Violated max discount policy")
    return Score(value=1.0)
```

**Production** (installable package):
```toml
# pyproject.toml
[project.entry-points."eva.evaluators"]
corporate_compliance = "myco_eva:check_compliance"
```

### Plugin Hook Lifecycle (pluggy)
```
before_eval(test, context)
  → run_eval(test, context) → Score
after_eval(test, score, context)
```

### Scoring Modes

Every evaluator returns `Score.value` (float 0.0–1.0). The `mode` determines how Eva acts on it:

| Mode | Behavior |
|---|---|
| `binary` | Passes only at 1.0, fails at anything less |
| `threshold` | Fails if `score.value < min_score` |
| `warn` | Never blocks — records the score and continues |

---

## Execution Model

### CLI (`eva run`)

```
load dataset (YAML/JSONL)
→ load evaluators (built-in + plugins)
→ execute tests (configurable concurrency)
→ score each response → Result
→ emit OTEL spans
→ persist to storage
→ TUI output + exit code
```

**Concurrency** — configured in `eva.yaml`, overridable per run:
```yaml
run:
  concurrency: 10   # async concurrent (default)
  # concurrency: 1  # sequential (debug)
  # workers: 4      # parallel processes
```

```bash
eva run --concurrency 1    # sequential
eva run --workers 4        # parallel
```

Internally: sequential = asyncio with concurrency 1, concurrent = asyncio semaphore, parallel = ProcessPoolExecutor.

### Gateway (`eva serve`)

```
client → Eva gateway
       → validate request against contract.request_schema
       → forward to target agent
       → intercept response
       → run evaluators (inline or ARQ async)
       → pass: return response to client
       → fail: inject hint, retry (up to max_retries)
       → still failing: return structured error
       → emit OTEL spans throughout
       → persist result to storage
```

**Two endpoints:**

`POST /v1/proxy` — forwards request, evaluates response only.

`POST /v1/contract/invoke` — validates request schema first, then evaluates response. Use this for A2A contract enforcement.

**Structured error (never a silent failure):**
```json
{
  "eva_status": "contract_violation",
  "attempts": 3,
  "violations": [
    {
      "evaluator": "corporate_compliance",
      "score": 0.0,
      "reason": "Violated max discount policy"
    }
  ],
  "request_id": "req_abc123",
  "trace_id": "otel_xyz789"
}
```

---

## Adapters

All adapters follow the same pattern: interface defined in Core, default implementation ships with Core, alternatives ship as plugins.

| Adapter | Default | Plugin alternatives |
|---|---|---|
| LLM | LiteLLM (2,600+ models) | — |
| Storage | SQLite (via SQLModel) | `eva-postgres` + any SQLAlchemy driver |
| State | Redis | any pluggable adapter |
| OTEL exporter | stdout | `eva-otlp` → Jaeger, Datadog, Grafana Tempo |

---

## Observability

Eva emits OpenTelemetry spans throughout every operation. Spans cover: request lifecycle, each evaluator execution, retries, final result.

Default exporter writes to stdout. Install `eva-otlp` to pipe to any OTEL-compatible backend.

Eva's storage adapter also accepts traces as a convenience — browse locally without an external backend.

---

## Tech Stack

| Concern | Choice | Rationale |
|---|---|---|
| CLI framework | Typer | Modern type-hint API, built on Click, less boilerplate |
| TUI | rich | Live progress, results tables, no extra deps |
| LLM routing | LiteLLM | 2,600+ models, stable, OpenAI-compatible interface |
| Plugin system | pluggy | pytest's own hook system — hook lifecycle, middleware-style wrapping |
| HTTP framework | FastAPI | Async-native, auto OpenAPI docs, pairs with ARQ |
| Task queue | ARQ | Async-first, Redis-only, lightweight — pairs naturally with FastAPI |
| ORM | SQLModel | Pydantic + SQLAlchemy — inherits all SQLAlchemy drivers |
| Tracing | OpenTelemetry | Standard wire format, no lock-in |
| Protocol | AGNTCY (OASF + ACP) | Interoperability hub over A2A and MCP |

---

## Boundaries

Eva enforces contracts. Eva does not own the business logic around them.

**Eva builds:** contract primitives, evaluator system, runner, gateway, official adapters.

**Ecosystem builds on Eva:** agent marketplaces, reputation scoring, dispute resolution, billing/escrow, domain-specific evaluator packages, web dashboard, framework integrations.

See `docs/ecosystem.md` for the full list of ecosystem opportunities.
