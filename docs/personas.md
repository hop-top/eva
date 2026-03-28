# Eva — Personas

Eva reuses or extends the shared hop-tool personas in
`/Users/jadb/.w/ideacrafterslabs/.docs/personas`.

These Eva personas are product-specific adaptations of those shared bases, not a separate taxonomy.

---

## Alex — AI Engineer

**Shared Base Persona:** `individuals/solo-developer.md`
**Relationship:** Extends the shared solo-developer persona from "single operator shipping a product
quickly" into "AI engineer shipping evals and CI gates quickly."

**Role:** AI/ML engineer at an early-stage startup.
**Context:** Builds LLM-powered product features; ships fast; CI is king.
**Primary tools:** `eva init`, `eva run`, `eva contract validate`.
**Success metric:** Contract violations caught in CI before merge.

### User Stories

- US-001: As Alex, I want to scaffold a new Eva project with `eva init` so that I can start
  writing evals without manual boilerplate.
- US-002: As Alex, I want to run a dataset of test cases against an LLM endpoint with `eva run`
  so that I can verify my prompt changes don't regress.
- US-003: As Alex, I want `eva run` to exit non-zero when any eval fails so that CI blocks the
  merge automatically.
- US-004: As Alex, I want to validate a contract YAML with `eva contract validate` so that I
  catch schema errors before committing.
- US-005: As Alex, I want to diff two contract versions with `eva contract diff` so that I can
  see breaking changes introduced by a prompt update.

---

## Sam — Platform Engineer

**Shared Base Persona:** `individuals/platform-engineer.md`
**Relationship:** Reuses the shared platform-engineer persona directly, with Eva-specific emphasis
on contract enforcement and AI gateway traffic.

**Role:** Platform / infrastructure engineer at a mid-size company.
**Context:** Runs Eva as a production API gateway in front of an LLM provider; on-call for uptime;
owns traffic capture, retention, and operational safety controls.
**Primary tools:** `eva serve`, retry config, auth headers, health endpoint, invocation storage,
sampling and redaction controls.
**Success metric:** Zero undetected failures reaching downstream consumers; production traces are
persisted safely enough to debug incidents without leaking sensitive data.

### User Stories

- US-006: As Sam, I want to start an Eva gateway with `eva serve` so that all LLM traffic passes
  through a validated proxy layer.
- US-007: As Sam, I want Eva to expose a `/health` endpoint so that my load-balancer can detect
  outages and route around them.
- US-008: As Sam, I want the proxy to retry failed requests with injected hints so that transient
  LLM quality failures are recovered without client involvement.
- US-009: As Sam, I want to configure auth token requirements on the gateway so that only
  authorised callers can invoke LLM endpoints through Eva.
- US-010: As Sam, I want per-request evaluator configuration on the `/v1/proxy` endpoint so that
  each integration can enforce its own quality contract at runtime.
- US-021: As Sam, I want Eva to persist raw request/response artifacts for gateway traffic so that
  operators can reconstruct exactly what happened during an incident.
- US-022: As Sam, I want Eva to ingest tool-call events from instrumented agents so that process
  failures can be debugged instead of inferred from final output alone.
- US-023: As Sam, I want configurable sampling, redaction, and retention on persisted artifacts so
  that production observability does not create an uncontrolled data liability.

---

## Jordan — Compliance Officer

**Shared Base Persona:** `individuals/platform-engineer.md`
**Relationship:** Extends the shared platform-engineer persona with regulated-industry audit,
evidence, and approval requirements. The operational foundation is the same; the acceptance bar is
higher.

**Role:** Compliance / risk officer at a regulated firm (finance or healthcare).
**Context:** Must demonstrate that AI outputs meet regulatory standards; needs audit evidence,
lineage, and historical comparisons across models and contracts.
**Primary tools:** `eva drift report`, OTEL traces, contract validation CI gate, invocation
querying, usage and comparison reports.
**Success metric:** Complete audit trail; zero undocumented PII exposure; drift alerts; model and
cost changes are attributable after the fact.

### User Stories

- US-011: As Jordan, I want to generate a drift report with `eva drift report` so that I can
  document when model behaviour deviates from the approved baseline.
- US-012: As Jordan, I want drift reports to be stored in a persistent DB so that I have a
  historical record for audits.
- US-013: As Jordan, I want Eva to emit OpenTelemetry traces for every eval run so that my SIEM
  can ingest and alert on quality regressions.
- US-014: As Jordan, I want contract YAML files to be version-controlled and diffable so that
  every change to an approved output contract is trackable.
- US-015: As Jordan, I want `eva drift report` to exit non-zero when no baseline runs exist so
  that missing-data gaps are surfaced rather than silently ignored.
- US-024: As Jordan, I want to inspect the exact request, response, contract version, and trace id
  for a historical invocation so that audit reviews do not rely on screenshots or operator memory.
- US-025: As Jordan, I want to compare quality, latency, and estimated cost across model versions
  so that a cheaper or newer model cannot be approved without evidence.
- US-026: As Jordan, I want to slice failures by evaluator, contract, model, and metadata tags so
  that compliance issues can be isolated to the affected cohort quickly.

---

## Taylor — OSS Contributor / Plugin Author

**Shared Base Persona:** `contributors/oss-go-developer.md`
**Relationship:** Extends the shared OSS contributor persona from Go infrastructure contributions to
Python plugin, adapter, and evaluator contributions in Eva.

**Role:** Open-source contributor; may also be an enterprise integrator building adapters.
**Context:** Extends Eva with custom evaluators or alternative storage backends; publishes to PyPI.
**Primary tools:** Plugin SDK (`EvaPlugin`, `EvaSpec`), `entry_points`, `eva_plugins.py`.
**Success metric:** Plugin loads cleanly, hook fires correctly, results surface in Eva output.

### User Stories

- US-016: As Taylor, I want to implement a custom evaluator by subclassing `EvaPlugin` so that I
  can encode domain-specific quality rules without forking Eva.
- US-017: As Taylor, I want to register my plugin via a `pyproject.toml` entry point so that it
  is auto-discovered when installed alongside Eva.
- US-018: As Taylor, I want to drop an `eva_plugins.py` file in the project root so that local
  one-off evaluators are loaded without packaging overhead.
- US-019: As Taylor, I want the `run_eval` hook to receive the full response and context dict so
  that my evaluator can make fine-grained decisions based on test metadata.
- US-020: As Taylor, I want plugin errors to be isolated and reported as a failed score rather
  than crashing the runner so that one bad plugin doesn't abort the whole suite.

---

## Riley — Evaluation Ops Lead

**Shared Base Persona:** `individuals/platform-engineer.md`
**Relationship:** Extends the shared platform-engineer persona into evaluation operations:
comparison workflows, review queues, annotation systems, and root-cause analysis across traces.

**Role:** Evaluation operations lead or AI reliability engineer.
**Context:** Owns the review loop between automated evals, production traces, and human judgment;
cares about dashboards, comparisons, and annotation quality.
**Primary tools:** run comparison CLI, failure slicing, usage reports, annotation workflows,
review queues.
**Success metric:** Automated and human eval signals can be reconciled in one system; regressions
are explainable by evidence, not intuition.

### User Stories

- US-027: As Riley, I want Eva to queue failed or sampled invocations for review so that humans can
  inspect the highest-risk outputs first.
- US-028: As Riley, I want to attach annotations and corrected outputs to an invocation so that Eva
  becomes the system of record for both automated and human evals.
- US-029: As Riley, I want to compare automated evaluator scores against human labels so that weak
  or misaligned evaluators can be identified and improved.
- US-030: As Riley, I want to inspect tool traces, retrieved context, and evaluator results in one
  place so that root-cause analysis is faster than reading scattered logs.
