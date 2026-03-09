# Eva Ecosystem — What Comes Next

Things identified during planning that Eva intentionally does NOT build, but enables through its interfaces. These are opportunities for the ecosystem, partners, or a marketplace tier of the Eva project.

---

## Built on Eva Core + Server

### Agent Marketplace
A platform where agents register contracts, consumers discover agents, and Eva enforces the contract at invocation time.

- Agent discovery and search (OASF registry browsable UI)
- Contract versioning and changelog
- Capability negotiation between agents
- Eva acts as the trust/enforcement layer — marketplace owns the business logic

### Reputation & Trust Scoring
Built on top of Eva's evaluation history (stored EvalResults over time).

- Per-agent reputation score derived from pass/fail history
- Trend analysis — is this agent getting better or worse?
- SLA tracking — is the agent meeting its latency contract?
- Eva provides the data, reputation system consumes it

### Dispute Resolution
For marketplace escrow use cases — when Agent A disputes Agent B's response.

- Eva's trace + score as evidence (immutable audit trail)
- Human review workflow for ambiguous cases
- Eva provides the record, dispute system provides the workflow

### Billing / Escrow
For paid agent services — payment conditional on contract fulfillment.

- Eva's `EvalResult` as the trigger for payment release
- Integration with payment rails (Stripe, etc.)
- Eva provides the signal, billing system acts on it

---

## Built on Eva Plugins Interface

### Domain-Specific Evaluator Marketplaces
Third-party evaluator packages for specific industries.

- `eva-evaluators-finance` — discount policy, regulatory compliance, KYC checks
- `eva-evaluators-healthcare` — HIPAA-aware content, medical accuracy
- `eva-evaluators-legal` — contract language, jurisdiction checks
- `eva-evaluators-ecommerce` — product policy, returns, inventory accuracy
- Community-published evaluators on PyPI

### Framework-Specific Adapters
Beyond official A2A and MCP plugins.

- `eva-langchain` — evaluate LangChain agent outputs natively
- `eva-crewai` — CrewAI multi-agent pipeline evaluation
- `eva-autogen` — AutoGen agent contract enforcement
- `eva-pydantic-ai` — Pydantic AI integration

### Observability Integrations
Beyond the official OTLP plugin.

- `eva-datadog` — native Datadog metrics + traces
- `eva-grafana` — Grafana dashboard templates
- `eva-sentry` — violation alerts via Sentry

---

## Built on Eva Gateway API

### Web Dashboard
A UI for browsing runs, traces, evaluator scores, and contract health.

- Leaderboard view — agent performance over time
- Trace explorer — drill into individual request lifecycles
- Contract diff viewer — visual comparison of contract versions
- Separate package: `eva-dashboard` (Next.js or Vite + shadcn/ui)

### CLI Companions
Tools that wrap `eva` for specific workflows.

- `eva-watch` — file watcher that re-runs evals on code change
- `eva-report` — generate HTML/PDF eval reports for stakeholders
- `eva-badge` — generate eval pass/fail badges for README

### Agent Hosting Integrations
For platforms that host agents.

- Deploy-time contract registration
- Runtime Eva gateway as a service (hosted, not self-managed)
- Automatic rollback if new agent version fails contracts

---

## Open Questions for Ecosystem Builders

- Who owns the OASF agent registry in a multi-tenant deployment?
- How do contracts get versioned and deprecated without breaking consumers?
- What's the trust model for third-party evaluator packages? (Sandboxing?)
- Can Eva's gateway be federated — multiple Eva instances coordinating?
