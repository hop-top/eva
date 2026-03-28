# Eva Observability Parity Plan
*2026-03-28*

## Goal

Close the gap between Eva's current contract enforcement and the richer observability workflows typically associated with LangSmith/Langfuse:

- persist raw request and response artifacts
- persist tool-call traces
- persist model identity, token usage, and estimated cost
- compare runs across model / contract / dataset versions
- slice failures by metadata and runtime dimensions
- support production ingestion, not just offline eval runs
- add human annotation support

This plan assumes Eva should remain contract-first and plugin-extensible. The objective is not to copy another product's UX. The objective is to make Eva's data model and query surface complete enough that those workflows are possible inside Eva.

---

## Persona and Story Coverage

This plan expands the existing product surface beyond the original CI, gateway, compliance, and
plugin-author personas. Those personas should be treated as Eva-specific extensions of the shared
hop-tool personas in `/Users/jadb/.w/ideacrafterslabs/.docs/personas`, not as a separate
taxonomy. It requires updates to:

- `docs/personas.md`
- `docs/user-stories.md`

### New or Expanded Story Coverage

- `US-021` to `US-023` extend Sam's production-gateway responsibilities to include artifact
  persistence, tool-event ingestion, and safe retention controls.
- `US-024` to `US-026` extend Jordan's audit and compliance responsibilities to include historical
  invocation inspection, model/cost comparison, and failure slicing.
- `US-027` to `US-030` add Riley, an evaluation-ops persona focused on review queues, annotation,
  evaluator-vs-human comparison, and root-cause analysis across traces and artifacts.

Every phase in this plan should map back to one or more of those user stories. No implementation
task should be accepted unless the corresponding story acceptance criteria are covered by tests,
CLI output, or storage/query behavior.

---

## Verified Current State

The following are already present:

- offline eval execution via `eva run`
- production gateway via `eva serve`
- SQLite-backed run persistence
- score-level drift reporting by `dataset + target`
- basic OTEL hooks and gateway trace IDs

The following are missing or incomplete in the current code:

- raw request / response persistence
- tool-call persistence
- explicit model identity on runs
- token / usage / cost persistence
- first-class invocation records
- first-class query surface for slicing failures
- human annotation storage
- runner OTEL instrumentation that matches the docs

---

## Design Principles

1. Preserve existing `Run` / `Result` semantics.
2. Add richer artifact storage without forcing all payloads into one wide JSON blob.
3. Support both offline runner and production gateway with the same core event model.
4. Keep storage pluggable. SQLite remains the default; Postgres can be added later.
5. Make large artifacts optional and redactable.
6. Treat tool traces, model usage, and annotations as first-class entities, not plugin-only metadata.

---

## Proposed Data Model

### Keep

- `Run`: suite-level summary
- `Result`: evaluator-level score record

### Add

#### `Invocation`

One row per evaluated agent call.

Fields:

- `invocation_id`
- `run_id` nullable for production-only traffic
- `source` enum: `offline_run | gateway_proxy | contract_invoke`
- `dataset`
- `test_id` nullable
- `target`
- `provider`
- `model`
- `model_version`
- `contract_name` nullable
- `request_id`
- `trace_id`
- `started_at`
- `duration_ms`
- `status` enum: `pass | fail | upstream_error | request_invalid`
- `request_artifact_id`
- `response_artifact_id`
- `retrieval_artifact_id` nullable
- `metadata_json`

#### `EvaluatorResult`

Split evaluator rows out of serialized run JSON for queryability.

Fields:

- `evaluator_result_id`
- `invocation_id`
- `evaluator`
- `mode`
- `min_score`
- `score_value`
- `passed`
- `reason`
- `duration_ms`
- `metadata_json`

#### `ToolCall`

One row per tool step.

Fields:

- `tool_call_id`
- `invocation_id`
- `step_index`
- `tool_name`
- `args_artifact_id`
- `result_artifact_id`
- `error_text`
- `started_at`
- `duration_ms`
- `status`
- `trace_id`
- `span_id`
- `metadata_json`

#### `UsageRecord`

Capture token and cost data per invocation and optionally per tool/model sub-call.

Fields:

- `usage_id`
- `invocation_id`
- `scope` enum: `agent | evaluator_judge | tool`
- `provider`
- `model`
- `prompt_tokens`
- `completion_tokens`
- `total_tokens`
- `estimated_cost_usd`
- `latency_ms`
- `raw_usage_json`

#### `Artifact`

Store raw payloads out-of-line.

Fields:

- `artifact_id`
- `kind` enum: `request | response | retrieval | tool_args | tool_result | annotation_attachment`
- `content_type`
- `storage_backend` enum: `inline | sqlite_blob | file`
- `text_content` nullable
- `json_content` nullable
- `blob_path` nullable
- `sha256`
- `size_bytes`
- `redacted`
- `created_at`

#### `Annotation`

Human review and gold labels.

Fields:

- `annotation_id`
- `invocation_id`
- `reviewer`
- `label`
- `score`
- `notes`
- `corrected_output_artifact_id` nullable
- `created_at`
- `metadata_json`

#### `DatasetVersion`

Reproducibility record.

Fields:

- `dataset_version_id`
- `dataset`
- `dataset_hash`
- `git_sha` nullable
- `source_path`
- `created_at`

#### `ContractVersion`

Snapshot the contract used for the run.

Fields:

- `contract_version_id`
- `contract_name`
- `contract_hash`
- `git_sha` nullable
- `artifact_id`
- `created_at`

---

## Phase Plan

## Phase 1: First-Class Invocation Storage

**Goal:** Persist enough data to answer "what exactly happened on this call?"

### Deliverables

- add `Invocation`, `EvaluatorResult`, and `Artifact` models
- persist raw request and response for both offline runner and gateway
- persist contract name, request id, trace id, and target
- preserve existing `Run` / `Result` outputs for backwards compatibility

### Files

- Edit: `core/models.py`
- Edit: `core/storage.py`
- Edit: `core/runner.py`
- Edit: `cli/main.py`
- Edit: `server/gateway/routes.py`
- Edit: `server/gateway/evaluator.py`
- Create: `tests/unit/test_invocation_storage.py`
- Create: `tests/server/test_gateway_persistence.py`

### Notes

- Do not remove `results_json` yet. Mark it compatibility-only.
- Introduce a new storage method:

```python
save_invocation(invocation, evaluator_results, artifacts)
```

- Gateway path should persist on both pass and fail paths.

### Acceptance

- A run can be reconstructed into raw request, raw response, evaluator results, and timestamps.
- A gateway request can be queried after completion even when it never belonged to an offline dataset run.
- Covers `US-021` and `US-024`.

---

## Phase 2: Model Identity, Usage, and Cost

**Goal:** Make comparisons by model and cost possible.

### Deliverables

- add `UsageRecord`
- extend `LiteLLMAdapter` to return both content and usage
- persist `provider`, `model`, `prompt_tokens`, `completion_tokens`, `total_tokens`
- add estimated cost calculation hook

### Files

- Edit: `core/llm.py`
- Edit: `core/models.py`
- Edit: `core/storage.py`
- Edit: `core/evaluators/llm_judge.py`
- Create: `core/costing.py`
- Create: `tests/unit/test_usage_capture.py`
- Create: `tests/unit/test_costing.py`

### Notes

- Current `LiteLLMAdapter.complete()` drops all metadata and only returns content. This must change.
- Use a structured return type, for example:

```python
class LLMCompletion(BaseModel):
    content: str
    provider: str | None
    model: str
    usage: dict
    raw_response: dict | None
```

- Preserve a convenience path for old callers if needed, but move internal callers to structured results.

### Acceptance

- Eva can answer:
  - which model produced this output?
  - how many tokens did it consume?
  - what was the estimated cost?
- Covers `US-025`.

---

## Phase 3: Tool-Call Event Capture

**Goal:** Make process/tool behavior auditable.

### Deliverables

- add `ToolCall`
- introduce a lightweight event API for agent wrappers and plugins
- persist `tool_name`, `args`, `result`, `error`, duration, trace linkage

### Files

- Edit: `core/plugins.py`
- Edit: `core/runner.py`
- Edit: `server/gateway/routes.py`
- Edit: `server/gateway/proxy.py`
- Create: `core/events.py`
- Create: `tests/unit/test_tool_event_capture.py`
- Create: `tests/server/test_gateway_tool_events.py`

### Notes

- Eva cannot infer hidden tool calls from final text alone.
- The production path needs either:
  - explicit tool events from the upstream agent
  - or a wrapped execution environment that emits those events

- Add a context event sink:

```python
context["event_sink"].emit_tool_call(...)
```

- For gateway users, document the required event contract. Without emitted tool events, process verification remains partial.

### Acceptance

- When an instrumented agent emits tool events, Eva persists them and links them to the invocation.
- Tool calls can be filtered by tool name, failure, latency, and contract.
- Covers `US-022` and `US-030`.

---

## Phase 4: Query Surface and Comparison UX

**Goal:** Make stored data usable without direct SQL.

### Deliverables

- add CLI compare/query commands
- support slicing by evaluator, model, contract, dataset version, tags, latency band
- support side-by-side run comparison

### Commands

- `eva runs list`
- `eva runs show --run-id ...`
- `eva invocations show --id ...`
- `eva compare --left ... --right ...`
- `eva failures list --evaluator ... --model ...`
- `eva usage report --dataset ... --target ...`

### Files

- Edit: `cli/main.py`
- Edit: `core/storage.py`
- Create: `core/query.py`
- Create: `tests/e2e/test_compare_command.py`
- Create: `tests/e2e/test_usage_report_command.py`

### Acceptance

- A user can compare two model versions without writing SQL.
- Failures can be sliced by metadata and runtime attributes from the CLI.
- Covers `US-025` and `US-026`.

---

## Phase 5: Production Ingestion Hardening

**Goal:** Make `eva serve` a real production observability sink.

### Deliverables

- persist gateway invocations on both pass and fail
- add configurable sampling
- add artifact redaction / retention controls
- add webhook payload enrichment with invocation ids

### Files

- Edit: `server/gateway/routes.py`
- Edit: `server/app.py`
- Edit: `ee/ee/server/webhooks.py`
- Create: `core/redaction.py`
- Create: `docs/production-observability.md`
- Create: `tests/server/test_gateway_sampling.py`

### Notes

- Storage pressure becomes real once raw payloads are stored.
- Add config for:
  - sample rate
  - artifact max size
  - redaction policy
  - retention TTL

### Acceptance

- Operators can safely run Eva in production without storing everything forever.
- Covers `US-023`.

---

## Phase 6: Human Annotation and Review Loop

**Goal:** Add the one major capability still absent even in the idealized architecture.

### Deliverables

- add `Annotation`
- support manual labels, corrected outputs, reviewer notes
- allow evaluator score vs human label comparison

### Commands

- `eva annotate add --invocation ...`
- `eva annotate list --invocation ...`
- `eva review queue --failed-only`

### Files

- Edit: `cli/main.py`
- Edit: `core/storage.py`
- Create: `tests/e2e/test_annotation_commands.py`
- Create: `docs/annotation-guide.md`

### Acceptance

- Eva can function as the system of record for both automated and human eval outcomes.
- Covers `US-027`, `US-028`, and `US-029`.

---

## Migration Strategy

1. Add new tables without removing old fields.
2. Continue writing existing `Run` / `Result` structures.
3. Backfill `Invocation` and `EvaluatorResult` from legacy `results_json` where possible.
4. Deprecate `results_json` only after query commands and migration helpers exist.

---

## Testing Strategy

### Unit

- storage round-trip for all new models
- LiteLLM usage extraction
- cost estimation
- event capture API
- redaction rules

### E2E

- offline run persists invocation artifacts
- gateway request persists invocation artifacts
- compare/query commands work against SQLite fixtures
- sampling and retention config behave correctly

### Integration

- OTLP export with invocation linkage
- Postgres storage adapter compatibility

---

## Risks

### 1. Storage blow-up

Raw payload persistence can explode SQLite size quickly.

Mitigation:

- artifact size caps
- optional out-of-line file storage
- configurable sampling
- retention policy

### 2. Trace inconsistency

Offline runner and gateway can diverge if they emit different artifact shapes.

Mitigation:

- use the same `Invocation` writer in both paths
- keep one canonical artifact schema

### 3. Tool-call ambiguity

Uninstrumented agents will still not expose real tool steps.

Mitigation:

- document the agent event API
- treat tool verification as "supported for instrumented agents"

### 4. Backwards compatibility

Changing the LLM adapter signature can ripple through evaluator code.

Mitigation:

- stage the adapter upgrade behind a new structured return type
- update judge evaluators in the same phase

---

## Recommended Build Order

1. Phase 1: invocation persistence
2. Phase 2: model / usage / cost capture
3. Phase 4: comparison/query surface
4. Phase 3: tool-call capture
5. Phase 5: production hardening
6. Phase 6: human annotation

This order gives immediate value after each phase:

- first visibility
- then economics
- then usability
- then deeper process traces
- then production scale
- then human review

---

## Definition of Done

Eva can answer all of the following from its own stored data:

- what was the exact request and response?
- which model produced it?
- what did it cost?
- how long did it take?
- which evaluators failed, and why?
- which tool calls happened, with what args/results/errors?
- how did this run differ from the previous model or prompt version?
- which failure patterns are increasing over time?
- what did a human reviewer decide about this output?

At that point, Eva is no longer only an enforcement layer with historical scores. It becomes a full evaluation record and analysis system.
