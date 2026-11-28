# Observability Data Model

What Eva stores about each evaluated call, and which command writes it.
All tables live in one SQLite file: `.eva/state.db` by default, or the
file given with `--db`. `eva serve` records gateway traffic in the same
file (see [Gateway traffic](#gateway-traffic)).

Entity diagram: [observability-data-model/entity-relationships-v1.mmd](observability-data-model/entity-relationships-v1.mmd).

---

## Overview

| Layer | Tables | Purpose |
|---|---|---|
| Run summary | `RunRecord` | One row per `eva run`: dataset, target, pass/fail, duration, serialized results. |
| Per-call record | `InvocationRecord`, `EvaluatorResultRecord` | One row per evaluated call (a dataset case or a gateway request), and one row per evaluator score on it. |
| Payloads | `ArtifactRecord` | Request, response and tool content, kept out of the invocation row. |
| Tool trace | `ToolCallRecord` | One row per tool call recorded for an invocation. |
| Economics | `UsageRecordRecord` | Token counts and (when present) estimated cost per model call. |
| Human review | `AnnotationRecord` | Reviewer labels on an invocation. |
| Per-case results | `CaseResultRecord` | First result per (dataset, target, case, case hash); see [`eva results`](cli-reference.md). |
| Version snapshots | `DatasetVersionRecord`, `ContractVersionRecord` | Defined in the schema; no current command writes them. |

`InvocationRecord` is the hub: evaluator results, tool calls, usage and
annotations all point at it through `invocation_id`.

---

## What `eva run` writes

For each scored case in dataset mode, `eva run` writes:

- one `InvocationRecord` (`source = offline_run`, `run_id` of the run,
  `test_id` = case id, `status` = `pass`, `fail` or `upstream_error`);
- one `EvaluatorResultRecord` per evaluator that applied;
- a `request` artifact (`{"input": ...}`) and a `response` artifact (the
  target's reply text), plus a `reasoning` artifact when a chat target
  returned reasoning text;
- for chat targets: one `UsageRecordRecord` (`scope = agent`) with the
  tokens the provider reported and the model latency, and one
  `ToolCallRecord` per tool call in the reply (see
  [Tool-call log](evaluators-reference.md#tool-call-log));
- one `CaseResultRecord` when the case is scored and the target answered.

`RunRecord` is written once at the end of the run.

`metadata_json` on the invocation carries `category`, `added` (from the
case metadata), `error` (upstream failure text), and for chat targets
`finish_reason`, `latency_ms` and `reasoning_artifact_id`.

`eva run` records token counts but no cost: `estimated_cost_usd` stays
empty, so cost figures in `eva usage report` and `eva compare` are
`$0.000000` for runs.

---

## Gateway traffic

`eva serve` opens the state db when it starts, once per process, and the
gateway routes record into it: `.eva/state.db` in the directory `eva serve`
is started from, or the file given with `eva serve --db <path>`. It is the
file `eva invocations`, `eva failures` and the other query commands read, so
point them at the same file (`--db <path>`) when you moved it. With
`--workers`, every worker writes to that one file. A gateway built in
code with `create_app()` and no `storage` argument records nothing.

| Route | Recorded | `source` | `contract_name` |
|---|---|---|---|
| `POST /v1/proxy` | Pass (`200`) and violation (`422`). Not recorded: invalid inline evaluator (`422`), upstream error (`502`). | `gateway_proxy` | `inline` |
| `POST /v1/contract/invoke` | Pass (`200`) and violation (`422`). Not recorded: request invalid (`400`), unknown contract (`404`), upstream error (`502`). | `contract_invoke` | the contract's name |
| `POST /v1/contract/evaluate` | Never. | | |

Per recorded request: one `InvocationRecord` (`status` `pass` or `fail`,
`request_id` and `trace_id` as returned in the response body, `run_id`
empty); a `request` and a `response` artifact; one `EvaluatorResultRecord`
per evaluator that ran, from the last attempt; and one `ToolCallRecord` per
tool call the upstream agent emitted through the event sink. On
`/v1/contract/invoke`, when the agent's reply is JSON with a `usage` object,
one `UsageRecordRecord` (`scope = agent`, with an estimated cost where the
model has a known price) points at the invocation through `invocation_id`.

`observability.sample_rate` in `eva.yaml` (default `1.0`) sets the fraction
of requests that get the artifacts, evaluator results and tool calls above.
Every other recorded request still gets its `InvocationRecord`, so counts
stay accurate; usage rows are written regardless of sampling.

---

## Entity reference

### InvocationRecord

`eva run` and `eva serve` (gateway routes) write these rows.

| Field | Type | Notes |
|---|---|---|
| `invocation_id` | string (UUID) | Primary key. |
| `run_id` | string or null | Foreign key to `RunRecord`. |
| `source` | string | `offline_run` (written by `eva run`); `gateway_proxy` (`/v1/proxy`) and `contract_invoke` (`/v1/contract/invoke`) are written by `eva serve`. |
| `dataset`, `test_id` | string or null | Dataset name and case id. |
| `target` | string | Target URL or id. |
| `provider`, `model`, `model_version` | string or null | Chat targets fill `provider` and `model`. |
| `contract_name` | string or null | Contract in effect, for gateway traffic (`inline` for `/v1/proxy`). |
| `request_id`, `trace_id` | string or null | Request and OTEL trace linkage. |
| `started_at`, `duration_ms` | datetime, int | Wall time of the call and its evaluation. |
| `status` | string | `pass`, `fail`, `upstream_error`, `request_invalid`. |
| `request_artifact_id`, `response_artifact_id`, `retrieval_artifact_id` | string or null | Foreign keys to `ArtifactRecord`. `eva run` fills the first two. |
| `metadata_json` | JSON string or null | See above. |

### EvaluatorResultRecord

| Field | Type | Notes |
|---|---|---|
| `evaluator_result_id` | string (UUID) | Primary key. |
| `invocation_id` | string | Foreign key to `InvocationRecord`. |
| `evaluator` | string | Evaluator name. |
| `mode`, `min_score` | string, float | The pass rule in effect (`binary`, `threshold`, `warn`). |
| `score_value`, `passed`, `reason` | float, bool, string | Score, derived pass/fail, evaluator reason. |
| `duration_ms` | int or null | Duration of the case, as recorded by the runner. |

### ArtifactRecord

| Field | Type | Notes |
|---|---|---|
| `artifact_id` | string (UUID) | Primary key. |
| `kind` | string | `request`, `response`, `reasoning`, `tool_args`, `tool_result`, `retrieval`, `annotation_attachment`. |
| `content_type` | string | MIME type. |
| `storage_backend` | string | `inline`, `sqlite_blob` or `file`. Current writers use `inline`. |
| `text_content`, `json_content`, `blob_path` | string or null | Payload, by backend. |
| `sha256`, `size_bytes` | string, int or null | `size_bytes` is set for request and response artifacts. |
| `redacted` | bool | Set by writers that redact before storing. |
| `created_at` | datetime | |

`tool_args` artifacts are written for tool calls that have arguments, and
`tool_result` artifacts for events that carry a result. Chat-target tool
calls are logged, not executed, so they have no result. Nothing writes
`retrieval` or `annotation_attachment` artifacts yet.

### ToolCallRecord

| Field | Type | Notes |
|---|---|---|
| `tool_call_id` | string (UUID) | Primary key. |
| `invocation_id` | string | Foreign key to `InvocationRecord`. |
| `step_index` | int | Position in the reply, from 0. Defaults to the event's position when the event has no `step_index`. |
| `tool_name` | string | |
| `args_artifact_id`, `result_artifact_id` | string or null | Foreign keys to `ArtifactRecord`. |
| `status`, `error_text` | string | `error` when the event carries an error, else `success`. |
| `started_at`, `duration_ms`, `trace_id`, `span_id` | | From the event. |
| `metadata_json` | JSON string or null | `{"raw_args": "..."}` when the arguments were not a valid JSON object. |

### UsageRecordRecord

| Field | Type | Notes |
|---|---|---|
| `usage_id` | string (UUID) | Primary key. |
| `invocation_id` | string | Foreign key to `InvocationRecord`. |
| `scope` | string | `agent` is written by `eva run` and by `/v1/contract/invoke`. `evaluator_judge` and `tool` are reserved. |
| `provider`, `model` | string | |
| `prompt_tokens`, `completion_tokens`, `total_tokens` | int or null | As the provider reported them. |
| `estimated_cost_usd` | float or null | Computed by `core/costing.py` where a writer calls it; otherwise null. |
| `latency_ms` | int or null | Model call latency. |
| `raw_usage_json` | JSON string or null | Provider usage object. |

### AnnotationRecord

| Field | Type | Notes |
|---|---|---|
| `annotation_id` | string (UUID) | Primary key. |
| `invocation_id` | string | Invocation the review refers to. |
| `reviewer`, `label`, `score`, `notes` | | Written by `eva annotate add`. |
| `corrected_output_artifact_id` | string or null | Foreign key to `ArtifactRecord`; no command sets it yet. |

An invocation can carry several annotations. See
[annotation-guide.md](annotation-guide.md).

### CaseResultRecord

Primary key `(dataset, target_id, case_id, case_hash)`. The first result
for a key stands; `eva results list|export|import|compare` read this
table. See the [`eva results`](cli-reference.md) section.

### DatasetVersionRecord and ContractVersionRecord

Hold a content hash, optional git SHA and source path (and, for contracts,
an artifact with the YAML). No command writes them today.

---

## Relationships

```
RunRecord (1) ---------------- (0..*) InvocationRecord
InvocationRecord (1) --------- (0..*) EvaluatorResultRecord
InvocationRecord (1) --------- (0..*) ToolCallRecord
InvocationRecord (1) --------- (0..*) UsageRecordRecord
InvocationRecord (1) --------- (0..*) AnnotationRecord
InvocationRecord (*) --------- (0..1) ArtifactRecord   [request, response, retrieval]
ToolCallRecord (*) ----------- (0..1) ArtifactRecord   [args, result]
AnnotationRecord (*) --------- (0..1) ArtifactRecord   [corrected output]
ContractVersionRecord (*) ---- (0..1) ArtifactRecord   [contract YAML]
```

`run_id` on `InvocationRecord` is nullable: gateway traffic has no parent
run.

---

## Querying

| Command | What it answers |
|---|---|
| `eva runs list` / `eva runs show --run-id <id>` | Runs, and one run with its invocations. |
| `eva invocations show --id <id>` | One invocation: artifacts, evaluator results, tool calls, usage. |
| `eva compare --left <run> --right <run>` | Two runs side by side. |
| `eva failures list` | Failed evaluator results, filtered by evaluator, model, contract, dataset. |
| `eva usage report` | Token and cost totals by model. |
| `eva annotate add` / `eva annotate list` | Add and list reviewer annotations. |
| `eva review queue` | Invocations without an annotation or with a failing evaluator result. |

Flags and output: [cli-reference.md](cli-reference.md). Python callers can
use the same queries from `core/query.py`.
