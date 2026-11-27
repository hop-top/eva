# eva.yaml Config Reference

Complete reference for `eva.yaml` dataset/contract configuration files.

---

## Dataset YAML

Controls which tests run, against which agent, with which evaluators.

### Full example

```yaml
name: refund_suite
target: http://localhost:8000/chat
evaluators:
  - name: contains
    mode: binary
  - name: no_pii
    mode: warn
tests:
  - id: test_01
    input: "Refund order 123"
  - id: test_02
    input: "What is my balance?"
    expected_output: "balance"
    metadata:
      category: account
```

### Root fields

| Field        | Type     | Required | Default | Description                          |
|--------------|----------|----------|---------|--------------------------------------|
| `name`       | `string` | Yes      | —       | Suite name; used in result storage.  |
| `target`     | `string` | Yes      | —       | Agent endpoint URL.                  |
| `evaluators` | `list`   | No       | `[]`    | Evaluator refs applied to each test. |
| `tests`      | `list`   | No       | `[]`    | List of `EvaTestCase` objects.       |

### `tests[*]` fields

| Field             | Type     | Required | Default | Description                      |
|-------------------|----------|----------|---------|----------------------------------|
| `id`              | `string` | Yes      | —       | Unique test identifier.          |
| `input`           | `string` | Yes      | —       | Prompt/request sent to agent.    |
| `expected_output` | `string` | No       | `null`  | Used by `contains` evaluator.    |
| `metadata`        | `object` | No       | `{}`    | Arbitrary key-value annotations. |

### `evaluators[*]` fields (dataset-level)

| Field       | Type     | Required | Default    | Description                             |
|-------------|----------|----------|------------|-----------------------------------------|
| `name`      | `string` | Yes      | —          | Evaluator ID (`contains`, `regex`, …).  |
| `mode`      | `string` | No       | `"binary"` | `binary` \| `threshold` \| `warn`.     |
| `min_score` | `float`  | No       | `1.0`      | Minimum score for `threshold` mode.     |

---

## Contract YAML

Defines behavioral guarantees for an agent; used by `eva contract validate/diff`.

### Full example

```yaml
name: refund_policy
provider: billing-agent
consumer: support-agent
request_schema:
  type: object
  required: [order_id]
  properties:
    order_id: { type: string }
evaluators:
  - name: json_schema_valid
    mode: binary
  - name: no_discount_violation
    mode: binary
retry_policy:
  max_retries: 3
  hint: "Ensure response is valid JSON; discount <= 20%"
  backoff_ms: 500
```

### Root fields

| Field            | Type     | Required | Default | Description                               |
|------------------|----------|----------|---------|-------------------------------------------|
| `name`           | `string` | Yes      | —       | Contract identifier.                      |
| `provider`       | `string` | Yes      | —       | Agent providing the service.              |
| `consumer`       | `string` | No       | `null`  | Agent consuming the service.              |
| `request_schema` | `object` | No       | `{}`    | JSON Schema for incoming request.         |
| `evaluators`     | `list`   | No       | `[]`    | Evaluator refs (same shape as dataset).   |
| `retry_policy`   | `object` | No       | —       | Retry config (see below).                 |

### `retry_policy` fields

| Field         | Type     | Default | Description                             |
|---------------|----------|---------|-----------------------------------------|
| `max_retries` | `int`    | `2`     | Max retry attempts on failure.          |
| `hint`        | `string` | `null`  | Injected into retry prompt as guidance. |
| `backoff_ms`  | `int`    | `0`     | Delay between retries (milliseconds).   |

---

## Judge (`eva.yaml`)

Model for Tier 2 (LLM-judge) evaluators, read by `eva run --dataset`.

```yaml
judge:
  model: openai/my-judge-model        # LiteLLM model id; unset = judge evaluators skipped
  base_url: http://localhost:11434/v1 # OpenAI-compatible endpoint (self-hosted, proxy)
  api_key_env: MY_JUDGE_KEY           # NAME of the env var holding the key
  timeout_s: 60                       # per-request timeout, seconds
  params: {}                          # extra LiteLLM kwargs (e.g. temperature)
```

| Key | Env override | Description |
|-----|--------------|-------------|
| `model` | `EVA_JUDGE_MODEL` | LiteLLM model id. None configured: judge evaluators are skipped with a reason, run not failed. |
| `base_url` | `EVA_JUDGE_BASE_URL` | OpenAI-compatible endpoint. Without `api_key_env`, a placeholder key is sent (ambient `OPENAI_API_KEY` is not forwarded). |
| `api_key_env` | | Env var NAME holding the key; never put the key in the file. Unset variable: exit `2`. |
| `timeout_s` | | Per-request timeout, seconds. |
| `params` | | Extra kwargs passed to LiteLLM. |

See [llm-evaluators.md](llm-evaluators.md).

---

## JSONL Dataset

Alternative to YAML for data-science workflows.

```
{"id": "t1", "input": "Refund order 123"}
{"id": "t2", "input": "Check balance", "expected_output": "balance"}
```

- One JSON object per line.
- Same fields as `tests[*]` in YAML format.
- `--target` flag **required** when using JSONL (no root `target` field).
- No `evaluators` inline — configure via `eva run` flags or plugins.

---

## Environment variables

| Variable           | Default                     | Description                     |
|--------------------|-----------------------------|---------------------------------|
| `EVA_STORAGE`      | `sqlite:///.eva/state.db`   | Storage backend connection URL. |
| `EVA_JUDGE_MODEL`  | _(none)_                    | LLM used for Tier 2 evaluators; overrides `judge.model`. |
| `EVA_JUDGE_BASE_URL` | _(none)_                  | OpenAI-compatible judge endpoint; overrides `judge.base_url`. |
| `OPENAI_API_KEY`   | _(none)_                    | Key for hosted OpenAI judge models (LiteLLM default). Not used with `judge.base_url`. |

Place in `.env` at project root; Eva loads it automatically via `python-dotenv`.
