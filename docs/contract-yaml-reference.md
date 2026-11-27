# Contract YAML Reference — Eva

A **Contract** defines the expected behavior and quality standards for an AI agent's interactions. This document provides a detailed reference for the YAML format used to define contracts in Eva.

---

## Example Contract

```yaml
name: refund_policy
provider: billing-agent
consumer: support-agent
request_schema:
  type: object
  required: [order_id]
  properties:
    order_id:
      type: string
evaluators:
  - name: json_schema_valid
    mode: binary
  - name: contains
    substring: "refund"
    mode: binary
retry_policy:
  max_retries: 3
  hint: "Ensure the response is valid JSON and confirms the refund status."
```

---

## Root Properties

| Property | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | **Yes** | Unique name for the contract. |
| `provider` | `string` | **Yes** | Identity of the agent providing the service. |
| `consumer` | `string` | No | Identity of the agent consuming the service. |
| `request_schema`| `object` | No | JSON Schema for validating the incoming request. |
| `evaluators` | `list` | No | List of evaluators to run against the agent's response. |
| `retry_policy` | `object` | No | Configuration for retrying failed interactions. |
| `prompt_field` | `string` | No | Request-body field holding the prompt for judge evaluators. See [Judge prompt](#judge-prompt-prompt_field). |

---

## Evaluator Properties

Each item in the `evaluators` list is a reference to a built-in or custom evaluator.

| Property | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | **Yes** | The name of the evaluator (e.g., `contains`, `regex`). |
| `mode` | `string` | No | Scoring mode: `binary` (default), `threshold`, or `warn`. |
| `min_score` | `float` | No | Minimum score required for `threshold` mode. Default: `1.0`. |

*Note: Individual evaluators may require additional properties based on their type (e.g., `substring` for the `contains` evaluator).*

---

## Retry Policy Properties

| Property | Type | Default | Description |
|---|---|---|---|
| `max_retries` | `int` | `2` | Number of times to retry a failed interaction. |
| `hint` | `string` | `None` | A text prompt injected into the retry request to guide the agent. |
| `backoff_ms` | `int` | `0` | Delay between retry attempts in milliseconds. |

---

## Judge prompt: `prompt_field`

LLM-judge evaluators (see [LLM Evaluators](llm-evaluators.md)) score a
`(prompt, response)` pair. The gateway has the response; `prompt_field` names
the request-body field that holds the prompt.

```yaml
name: support_reply
provider: http://agent:8000/respond
prompt_field: question
evaluators:
  - name: relevance
    mode: threshold
    min_score: 0.7
```

| Property | Type | Required | Description |
|---|---|---|---|
| `prompt_field` | `string` | No | Name of a top-level key of the request `body`. Its string value is the prompt handed to judge evaluators. |

- Top-level key only: no nested or dotted paths (same lookup rule as the
  `field:` option of `regex`, `contains` and `equals`).
- The value must be a string. A body without the key, or with a non-string
  value, skips the judge evaluators for that request (reported in `skipped`).
- Without `prompt_field`, judge evaluators are skipped.
- Contracts without judge evaluators ignore the key.

See [Judge evaluators in the gateway](llm-evaluators.md#judge-evaluators-in-the-gateway)
for configuration, what is skipped and why, and retry cost.

---

## Best Practices

1.  **Strict Request Schemas**: Always define a `request_schema` to prevent malformed inputs from reaching your agent.
2.  **Specific Evaluators**: Use specific evaluators like `json_schema_valid` if your agent is expected to return structured data.
3.  **Actionable Hints**: Write `retry_policy.hint` as if you were coaching the agent. Instead of "Fix it," use "The response must contain a valid refund ID in the 'id' field."
4.  **Use `warn` for Monitoring**: For new or experimental evaluators, use `mode: warn` to collect data without gating your pipeline.

---

## Contracts for exec-step output (`flo` exec step)

Contracts can validate any text/JSON artifact — not just live agent
responses. A common pattern is gating CI smoke tests on the recorded output
of a CLI step (see [flo](https://github.com/hop-top/flo) and the
[smoke-testing cookbook](smoke-testing-cli-with-flow-exec.md)).

The input to the contract is the exec step's structured output, typically
shaped like:

```json
{
  "exit_code": 0,
  "stdout": "Created task T-0734\nStatus: TODO\n",
  "stderr": ""
}
```

Example contract for that artifact:

```yaml
name: tlc_task_create_smoke
provider: tlc
evaluators:
  - name: exit_code
    expected: 0
  - name: regex
    pattern: 'Created task T-[0-9]{4}'
    field: stdout
  - name: contains
    substring: 'TODO'
    field: stdout
```

> **Note:** `field:` routing is honored by `status_code` (alias
> `exit_code`), `equals`, `regex`, and `contains`. For `regex` and `contains`,
> when `field` is set the input is parsed as a JSON object and the check runs
> against that top-level field's string value only; text elsewhere in the
> payload is ignored. The check scores 0.0 (never raises) when the input is not
> a JSON object, the field is missing, or the field's value is not a string.
> Without `field`, the whole input string is evaluated. Nested or dotted paths
> are not supported.

Run the contract against a recorded output via the standalone CLI:

```bash
eva run --contract contracts/tlc_task_create.yaml --input artifacts/output.json
```

This validates the recording without booting an agent, an Eva server, or the
upstream CLI under test — making the gate fast, hermetic, and CI-friendly.
