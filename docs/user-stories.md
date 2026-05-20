# Eva — User Stories

All user stories grouped by persona. IDs are stable; append new stories at end of each group.

---

## Alex — AI Engineer

Associated Eva persona: [Alex — AI Engineer](./personas.md)
Shared base persona: `individuals/solo-developer.md` (maintained in the shared hop-top personas library, outside this repo)

| ID     | Story |
|--------|-------|
| US-001 | As Alex, I want to scaffold a new Eva project with `eva init` so that I can start writing |
|        | evals without manual boilerplate. |
| US-002 | As Alex, I want to run a dataset of test cases against an LLM endpoint with `eva run` so |
|        | that I can verify my prompt changes don't regress. |
| US-003 | As Alex, I want `eva run` to exit non-zero when any eval fails so that CI blocks the merge |
|        | automatically. |
| US-004 | As Alex, I want to validate a contract YAML with `eva contract validate` so that I catch |
|        | schema errors before committing. |
| US-005 | As Alex, I want to diff two contract versions with `eva contract diff` so that I can see |
|        | breaking changes introduced by a prompt update. |

---

## Alex — Developer & Evaluator User (Metrics Expansion)

Associated Eva persona: [Alex — AI Engineer](./personas.md)
Shared base persona: `individuals/solo-developer.md` (maintained in the shared hop-top personas library, outside this repo)

| ID     | Story |
|--------|-------|
| [US-031](./stories/US-031-rag-evaluation.md) | As Alex, I want to evaluate RAG pipeline quality using faithfulness, contextual relevancy, |
|        | precision, recall, answer relevancy, and RAGAS composite scores so that I can identify retrieval |
|        | and grounding failures before they reach users. |
| [US-032](./stories/US-032-tool-use-evaluation.md) | As Alex, I want to evaluate tool usage quality and plan execution so that agentic failures are |
|        | caught before deployment. |
| [US-033](./stories/US-033-multi-turn-evaluation.md) | As Alex, I want to evaluate multi-turn conversations so that issues like knowledge loss, |
|        | incomplete resolution, and persona drift are detected across conversation history. |
| [US-034](./stories/US-034-content-quality-evaluation.md) | As Alex, I want dedicated evaluators for bias, toxicity, summarization quality, prompt |
|        | alignment, and goal accuracy so that nuanced content quality issues are measured independently. |
| [US-035](./stories/US-035-image-evaluation.md) | As Alex, I want to evaluate image generation and image-grounded responses so that visual output |
|        | quality is verifiable alongside text quality. |

---

## Sam — Platform Engineer

Associated Eva persona: [Sam — Platform Engineer](./personas.md)
Shared base persona: `individuals/platform-engineer.md` (maintained in the shared hop-top personas library, outside this repo)

| ID     | Story |
|--------|-------|
| US-006 | As Sam, I want to start an Eva gateway with `eva serve` so that all LLM traffic passes |
|        | through a validated proxy layer. |
| US-007 | As Sam, I want Eva to expose a `/health` endpoint so that my load-balancer can detect |
|        | outages and route around them. |
| US-008 | As Sam, I want the proxy to retry failed requests with injected hints so that transient |
|        | LLM quality failures are recovered without client involvement. |
| US-009 | As Sam, I want to configure auth token requirements on the gateway so that only authorised |
|        | callers can invoke LLM endpoints through Eva. |
| US-010 | As Sam, I want per-request evaluator configuration on the `/v1/proxy` endpoint so that |
|        | each integration can enforce its own quality contract at runtime. |
| [US-021](./stories/US-021-gateway-artifact-storage.md) | As Sam, I want Eva to persist raw request/response artifacts for gateway traffic so that |
|        | operators can reconstruct exactly what happened during an incident. |
| [US-022](./stories/US-022-tool-call-ingestion.md) | As Sam, I want Eva to ingest tool-call events from instrumented agents so that process |
|        | failures can be debugged instead of inferred from final output alone. |
| [US-023](./stories/US-023-sampling-redaction-retention.md) | As Sam, I want configurable sampling, redaction, and retention on persisted artifacts so |
|        | that production observability does not create an uncontrolled data liability. |

---

## Jordan — Compliance Officer

Associated Eva persona: [Jordan — Compliance Officer](./personas.md)
Shared base persona: `individuals/platform-engineer.md` (maintained in the shared hop-top personas library, outside this repo)

| ID     | Story |
|--------|-------|
| US-011 | As Jordan, I want to generate a drift report with `eva drift report` so that I can document |
|        | when model behaviour deviates from the approved baseline. |
| US-012 | As Jordan, I want drift reports to be stored in a persistent DB so that I have a historical |
|        | record for audits. |
| US-013 | As Jordan, I want Eva to emit OpenTelemetry traces for every eval run so that my SIEM can |
|        | ingest and alert on quality regressions. |
| US-014 | As Jordan, I want contract YAML files to be version-controlled and diffable so that every |
|        | change to an approved output contract is trackable. |
| US-015 | As Jordan, I want `eva drift report` to exit non-zero when no baseline runs exist so that |
|        | missing-data gaps are surfaced rather than silently ignored. |
| [US-024](./stories/US-024-historical-invocation-inspection.md) | As Jordan, I want to inspect the exact request, response, contract version, and trace id |
|        | for a historical invocation so that audit reviews do not rely on screenshots or operator |
|        | memory. |
| [US-025](./stories/US-025-model-quality-latency-cost-compare.md) | As Jordan, I want to compare quality, latency, and estimated cost across model versions so |
|        | that a cheaper or newer model cannot be approved without evidence. |
| [US-026](./stories/US-026-failure-slicing.md) | As Jordan, I want to slice failures by evaluator, contract, model, and metadata tags so |
|        | that compliance issues can be isolated to the affected cohort quickly. |

---

## Taylor — OSS Contributor / Plugin Author

Associated Eva persona: [Taylor — OSS Contributor / Plugin Author](./personas.md)
Shared base persona: `contributors/oss-go-developer.md` (maintained in the shared hop-top personas library, outside this repo)

| ID     | Story |
|--------|-------|
| US-016 | As Taylor, I want to implement a custom evaluator by subclassing `EvaPlugin` so that I can |
|        | encode domain-specific quality rules without forking Eva. |
| US-017 | As Taylor, I want to register my plugin via a `pyproject.toml` entry point so that it is |
|        | auto-discovered when installed alongside Eva. |
| US-018 | As Taylor, I want to drop an `eva_plugins.py` file in the project root so that local |
|        | one-off evaluators are loaded without packaging overhead. |
| US-019 | As Taylor, I want the `run_eval` hook to receive the full response and context dict so that |
|        | my evaluator can make fine-grained decisions based on test metadata. |
| US-020 | As Taylor, I want plugin errors to be isolated and reported as a failed score rather than |
|        | crashing the runner so that one bad plugin doesn't abort the whole suite. |

---

## Riley — Evaluation Ops Lead

Associated Eva persona: [Riley — Evaluation Ops Lead](./personas.md)
Shared base persona: `individuals/platform-engineer.md` (maintained in the shared hop-top personas library, outside this repo)

| ID     | Story |
|--------|-------|
| [US-027](./stories/US-027-review-queue.md) | As Riley, I want Eva to queue failed or sampled invocations for review so that humans can |
|        | inspect the highest-risk outputs first. |
| [US-028](./stories/US-028-annotations-and-corrections.md) | As Riley, I want to attach annotations and corrected outputs to an invocation so that Eva |
|        | becomes the system of record for both automated and human evals. |
| [US-029](./stories/US-029-evaluator-vs-human.md) | As Riley, I want to compare automated evaluator scores against human labels so that weak or |
|        | misaligned evaluators can be identified and improved. |
| [US-030](./stories/US-030-root-cause-triage.md) | As Riley, I want to inspect tool traces, retrieved context, and evaluator results in one |
|        | place so that root-cause analysis is faster than reading scattered logs. |

---

## Coverage Matrix

| US ID  | Persona | Primary CLI / API          | E2E Test File                  |
|--------|---------|----------------------------|-------------------------------|
| US-001 | Alex    | `eva init`                 | test_init.py                  |
| US-002 | Alex    | `eva run`                  | test_run.py                   |
| US-003 | Alex    | `eva run` exit code        | test_run.py                   |
| US-004 | Alex    | `eva contract validate`    | test_contract_validate.py     |
| US-005 | Alex    | `eva contract diff`        | test_contract_diff.py         |
| US-006 | Sam     | `eva serve`                | test_serve_command.py         |
| US-007 | Sam     | `/health`                  | test_serve_command.py         |
| US-008 | Sam     | `/v1/proxy` retry          | test_server_e2e.py            |
| US-009 | Sam     | gateway auth               | test_serve_command.py         |
| US-010 | Sam     | `/v1/proxy` evaluators     | test_server_e2e.py            |
| US-011 | Jordan  | `eva drift report`         | test_drift_command.py         |
| US-012 | Jordan  | drift DB persistence       | test_drift_command.py         |
| US-013 | Jordan  | OTEL traces                | (integration; future)         |
| US-014 | Jordan  | `eva contract diff`        | test_contract_diff.py         |
| US-015 | Jordan  | `eva drift report` exit 1  | test_drift_command.py         |
| US-016 | Taylor  | plugin SDK / `eva run`     | test_plugin_e2e.py            |
| US-017 | Taylor  | entry_points discovery     | (unit; future)                |
| US-018 | Taylor  | `eva_plugins.py` local     | test_plugin_e2e.py            |
| US-019 | Taylor  | `run_eval` hook context    | test_plugin_e2e.py            |
| US-020 | Taylor  | plugin error isolation     | test_plugin_e2e.py            |
| US-021 | Sam     | gateway artifact storage   | test_gateway_persistence.py   |
| US-022 | Sam     | tool-call ingestion        | test_gateway_tool_events.py   |
| US-023 | Sam     | sampling / redaction       | test_gateway_sampling.py      |
| US-024 | Jordan  | `eva invocations show`     | (future; plan)                |
| US-025 | Jordan  | `eva compare`              | test_compare_command.py       |
| US-026 | Jordan  | `eva failures list`        | (future; plan)                |
| US-027 | Riley   | `eva review queue`         | (future; plan)                |
| US-028 | Riley   | `eva annotate add/list`    | test_annotation_commands.py   |
| US-029 | Riley   | evaluator vs human review  | (future; plan)                |
| US-030 | Riley   | invocation triage workflow | (future; plan)                |
| US-031 | Alex    | RAG evaluators             | test_rag_evaluators.py (future)        |
| US-032 | Alex    | Tool/agentic evaluators    | test_tool_evaluators.py (future)       |
| US-033 | Alex    | Multi-turn evaluators      | test_multi_turn_evaluators.py (future) |
| US-034 | Alex    | Content quality evaluators | test_content_evaluators.py (future)    |
| US-035 | Alex    | Image evaluators           | test_image_evaluators.py (future)      |
