# Built-in Evaluators Reference — Eva

Evaluators analyze an agent's response and return a **Score** (0.0 to 1.0). In Phase 1, Eva includes a set of **Tier 1 (Deterministic)** evaluators that run locally and do not require LLM calls.

---

## `contains`

Checks if the agent's response contains a specific substring.

### Configuration Properties:
| Property | Type | Required | Description |
|---|---|---|---|
| `substring` | `string` | **Yes** | The text to search for. |
| `case_sensitive` | `boolean` | No | Whether the search is case-sensitive. Default: `true`. |

### Example Contract Usage:
```yaml
evaluators:
  - name: contains
    substring: "refund"
    case_sensitive: false
```

---

## `regex`

Matches the agent's response against a regular expression pattern.

### Configuration Properties:
| Property | Type | Required | Description |
|---|---|---|---|
| `pattern` | `string` | **Yes** | The regular expression to match. |

### Example Contract Usage:
```yaml
evaluators:
  - name: regex
    pattern: "Order #[0-9]{4,6}"
```

---

## `json_schema_valid`

Validates that the agent's response is valid JSON and satisfies a specific JSON Schema.

### Configuration Properties:
| Property | Type | Required | Description |
|---|---|---|---|
| `schema` | `object` | **Yes** | The JSON Schema to validate against. |

### Example Contract Usage:
```yaml
evaluators:
  - name: json_schema_valid
    schema:
      type: object
      required: [status, refund_id]
      properties:
        status: { type: string }
        refund_id: { type: string }
```

---

## `no_pii`

Detects common Personal Identifiable Information (PII) patterns in the agent's response.

### Patterns Detected:
- Email addresses
- Social Security Numbers (SSN)
- Credit card numbers
- Phone numbers

### Example Contract Usage:
```yaml
evaluators:
  - name: no_pii
    mode: binary
```

---

## `status_code` / `exit_code`

Asserts that a flow-exec step's `exit_code` (or HTTP-style `status_code`) field matches an
expected integer or falls within an allowed set. `exit_code` is registered as an alias for
`status_code` — both names resolve to the same evaluator class. Use whichever reads more
naturally for your contract; `exit_code` matches the field emitted by tlc's `exec` step
type, while `status_code` mirrors HTTP convention.

The evaluator receives the step output as a JSON-encoded string. It looks up `exit_code`
first, then falls back to `status_code`. Booleans are rejected (Python's `bool` is an int
subclass — guarded explicitly).

### Configuration Properties:
| Property | Type | Required | Description |
|---|---|---|---|
| `step` | `string` | No | Identifier of the flow step whose output to evaluate. Used by the runner to route the correct payload; metadata only at the evaluator level. |
| `expected` | `int` | One of | Single integer the field must equal exactly. |
| `expected_in` | `list[int]` | One of | Set of acceptable integers. Mutually exclusive with `expected`. |

Exactly one of `expected` or `expected_in` must be provided.

### Example Contract Usage:
```yaml
evaluators:
  - type: status_code
    step: cli-version
    expected: 0
  # exit_code alias — same behavior:
  - type: exit_code
    step: cli-version
    expected: 0
  # allowed set:
  - type: status_code
    step: cli-version
    expected_in: [0, 2]
```

> **Note:** `step_status` was historically referenced in some upstream tlc fixtures
> but never landed in eva. Use `status_code` (or its `exit_code` alias) for exit-code
> checks — those fixtures should be rewritten to point at `status_code`.

---

## `equals`

Generic field-equality evaluator. Asserts that a named field in a JSON step-output payload
equals an expected literal. Supports any JSON-representable type: string, int, float, bool,
list, dict, null.

Type checking is strict (`str` vs `int` is a mismatch) with one exception: int/float
cross-comparison is allowed because JSON numbers may decode either way. Booleans are kept
distinct from integers.

### Configuration Properties:
| Property | Type | Required | Description |
|---|---|---|---|
| `field` | `string` | **Yes** | Name of the field in the step output to compare. |
| `expected` | `any` | **Yes** | Literal value the field must equal. `null` is valid. |
| `step` | `string` | No | Identifier of the flow step whose output to evaluate. |

### Example Contract Usage:
```yaml
evaluators:
  - type: equals
    step: parse-config
    field: log_level
    expected: "info"
  - type: equals
    step: parse-config
    field: retries
    expected: 3
```

---

## `latency`

*(Planned for Phase 1 Integration)*
Measures the response time and returns 1.0 if it falls within the allowed range.

---

## Tier 2 (LLM-as-Judge)

Requires `EVA_JUDGE_MODEL` in env. Full reference: [llm-evaluators.md](llm-evaluators.md).

**General:** `relevance`, `hallucination`, `tone`, `task_completion`, `safety`, `bias`,
`toxicity`, `summarization`, `prompt_alignment`, `goal_accuracy`, `geval`

**RAG:** `faithfulness`, `answer_relevancy`, `contextual_relevancy`, `contextual_precision`,
`contextual_recall`, `ragas`

**Tool-use / Agentic:** `tool_correctness`, `argument_correctness`, `tool_use`,
`step_efficiency`, `plan_adherence`, `plan_quality`

**Multi-turn:** `knowledge_retention`, `conversation_completeness`, `turn_relevancy`,
`turn_faithfulness`, `role_adherence`

**Image / Multimodal:** `text_to_image`, `image_editing`, `image_coherence`,
`image_helpfulness`, `image_reference`
