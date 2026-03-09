# Project Eva (`hop-top/eva`)
**The Operating System for Reliable AI Agents**

Eva is a distributed, extensible framework for testing, routing, and validating LLM-based agents. It transitions AI Quality Assurance from a passive "dashboard vibe-check" into an active, programmable middleware that enforces contracts between agents and users (A2A/B2C).

---

## 1. Core Philosophy

1. **Convention over Configuration (CoC):** Near-zero configuration to get started. By default, Eva uses SQLite for local state and LiteLLM for agnostic model routing. If you run `eva run`, it auto-discovers datasets in `./evals` and uses `gpt-4o-mini` if `OPENAI_API_KEY` is present.
2. **Infinite Extensibility:** While defaults are opinionated, every layer (Storage, LLM, Evaluators, Protocols) is an interface. You can inject custom Python code by simply dropping it into an `./eva_plugins/` directory.
3. **Doc-Driven & Test-Driven (Red/Green/Refactor):** UX is paramount. We write the User Guide and CLI/API documentation *first*. Then, we write E2E tests asserting that the CLI outputs exactly what the docs promise (Red). Finally, we write the implementation (Green).

---

## 2. Extensibility & Configuration Model

Eva achieves maximum customizability without bloating the core engine through **Auto-Discovery and Adapter Interfaces**.

### The "Zero-Config" Default
Simply having an `.env` file makes Eva work:
```env
EVA_STORAGE=sqlite:///.eva/state.db
EVA_JUDGE_MODEL=openai/gpt-4o
```

### The "Infinite Config" Extensibility (Custom Evaluators)
Users can extend Eva by placing a Python file in their repository (e.g., `eva_plugins.py`). Eva auto-discovers decorators:

```python
# eva_plugins.py
from eva.core import evaluator, Score

@evaluator(name="corporate_compliance", category="heuristic")
def check_corporate_compliance(response: str, context: dict) -> Score:
    """Fails instantly if the agent promises a discount > 20%"""
    if "30% off" in response:
        return Score(value=0.0, reason="Violated max discount policy", metadata={"critical": True})
    return Score(value=1.0)
```

---

## 3. Usage Samples (The "Doc" Phase)

Here is how end-users will experience Eva across different stages of the SDLC.

### A. The CLI (Local Development)
Developers use Eva locally like `pytest`. 

```bash
$ pip install eva-core

# Initialize zero-config structure
$ eva init
Created ./evals/
Created ./eva_plugins.py
Created .env

# Run evaluations against a local agent
$ eva run --dataset ./evals/refunds.yaml --target http://localhost:8000/chat
✅ Test refund_01 (1.2s)
❌ Test refund_02 (0.8s) - Failed: Corporate Compliance (Violated max discount policy)
✅ Test refund_03 (2.1s)

Results: 2/3 Passed.
Saved report to .eva/reports/run_8912.xml
```

### B. CI/CD Integration (GitHub Actions)
Eva runs as a Quality Gate on every Pull Request.

```yaml
# .github/workflows/eva-eval.yml
name: Agent Evaluation
on: [pull_request]

jobs:
  evaluate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Start Local Agent
        run: docker-compose up -d my-agent
      - name: Run Eva
        uses: hop-top/eva-action@v1
        with:
          dataset: './evals/regression_suite.yaml'
          target: 'http://localhost:8000'
          judge-model: 'anthropic/claude-3-5-sonnet'
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

### C. Middleware Routing & Self-Healing (API)
In production, Eva runs as a sidecar/gateway. It intercepts traffic, evaluates it on the fly, and retries if the agent hallucinates.

```python
# FastAPI app sitting behind Eva
import httpx

# The client app talks to EVA, not the agent directly.
response = httpx.post("https://eva-gateway.internal/v1/route", json={
    "target_agent": "billing-bot",
    "prompt": "Refund order 123",
    "enforce_evaluators": ["json_schema_valid", "corporate_compliance"],
    "fallback_strategy": {
        "max_retries": 2,
        "hint": "Ensure output is valid JSON and discount is <= 20%"
    }
})
```

### D. A2A Contract Checking (Protocol Level)
Agent A (Consumer) requests data from Agent B (Provider). Eva sits in the middle and enforces a YAML contract.

**The Contract (`contracts/flight_search.yaml`):**
```yaml
name: flight_search
provider: agent-travel
consumer: agent-expense
request_schema:
  type: object
  required: [destination, date, max_price]
response_evaluators:
  - type: deterministic
    rule: "response.price <= request.max_price"
```

**The Invocation:**
```bash
# Agent A calls Agent B through Eva's Contract Endpoint
curl -X POST https://eva-gateway/v1/contract/invoke \
  -H "Authorization: Bearer agent-a-token" \
  -d '{
    "contract": "flight_search",
    "payload": {"destination": "NYC", "date": "2026-04-01", "max_price": 500}
  }'
# Eva verifies the payload, forwards to Agent B, intercepts Agent B's response, 
# evaluates the price rule, and only returns the response if it passes.
```

---

## 4. Development Methodology & Phased Rollout

We will build Eva using the **Documentation -> E2E Test -> Code** lifecycle.

### Phase 1: The CLI Engine (Foundation)
*   **Doc:** Write the CLI `README.md` and expected terminal outputs.
*   **Test:** Write Python `subprocess` tests that execute `eva init` and `eva run` and assert the standard output and exit codes (Red).
*   **Code:** Implement the CLI via `Typer`, the plugin auto-discovery mechanism, and the basic Deterministic Evaluators.

### Phase 2: Agnostic Adapters & LLM Judging
*   **Doc:** Write docs on how to configure LiteLLM and SQLite vs Postgres.
*   **Test:** Write tests mocking LiteLLM responses to ensure Evaluators score correctly based on LLM outputs (Red).
*   **Code:** Implement `eva_core/adapters/llm.py` and `eva_core/adapters/storage.py`. Implement the LLM-as-a-judge evaluator.

### Phase 3: The API & A2A Middleware
*   **Doc:** Write the OpenAPI spec/Swagger documentation for the Gateway routing, self-healing retries, and A2A contracts.
*   **Test:** Write `httpx` integration tests validating that a bad agent response triggers a middleware retry, and a contract violation returns a `422` to the consumer (Red).
*   **Code:** Implement `eva_server/` using FastAPI. Add Redis/Celery for async job queueing to handle long-running A2A tasks.

### Phase 4: TypeScript Web Dashboard
*   **Doc:** Define UI mockups/components in Markdown.
*   **Test:** Generate TS clients from the OpenAPI spec. Write Playwright E2E tests for navigating the Leaderboard and Trace explorer.
*   **Code:** Build the Next.js/Vite frontend using `shadcn/ui`.

---

## 5. Repository Structure (Recap)
```
hop-top/eva/
├── docs/                 # Built FIRST (DDD)
├── tests/                # Built SECOND (TDD E2E)
│   ├── e2e_cli/
│   └── e2e_api/
├── eva_cli/              # Typer CLI
├── eva_core/             # Pydantic Models, Evaluators, Pluggable Adapters
├── eva_server/           # FastAPI Gateway, Middleware, Queues
├── eva_web/              # Generated TS API Client, React Dashboard
└── docker-compose.yml    # Zero-config local runner
```