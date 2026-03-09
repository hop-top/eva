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

## Best Practices

1.  **Strict Request Schemas**: Always define a `request_schema` to prevent malformed inputs from reaching your agent.
2.  **Specific Evaluators**: Use specific evaluators like `json_schema_valid` if your agent is expected to return structured data.
3.  **Actionable Hints**: Write `retry_policy.hint` as if you were coaching the agent. Instead of "Fix it," use "The response must contain a valid refund ID in the 'id' field."
4.  **Use `warn` for Monitoring**: For new or experimental evaluators, use `mode: warn` to collect data without gating your pipeline.
