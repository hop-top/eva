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

## `status_code`

*(Planned for Phase 1 Integration)*
Validates that the HTTP response code from the agent matches a set of expected values.

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
