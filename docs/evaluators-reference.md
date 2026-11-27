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
| `field` | `string` | No | Top-level field of a JSON object input to search instead of the whole input. Scores 0.0 if the input is not a JSON object, the field is missing, or its value is not a string. |

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
| `field` | `string` | No | Top-level field of a JSON object input to match instead of the whole input. Scores 0.0 if the input is not a JSON object, the field is missing, or its value is not a string. |

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

Asserts that the `exit_code` (or HTTP-style `status_code`) field matches an
expected integer or falls within an allowed set. `exit_code` is registered as an alias for
`status_code` — both names resolve to the same evaluator class. Use whichever reads more
naturally for your contract; `exit_code` reads as a command's exit status, while `status_code` mirrors HTTP convention.

The evaluator receives the input as a JSON-encoded string. It looks up `exit_code`
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
  - name: status_code
    step: cli-version
    expected: 0
  # exit_code alias — same behavior:
  - name: exit_code
    step: cli-version
    expected: 0
  # allowed set:
  - name: status_code
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
  - name: equals
    step: parse-config
    field: log_level
    expected: "info"
  - name: equals
    step: parse-config
    field: retries
    expected: 3
```

---

## `word_count`

Counts whitespace-separated tokens in the response and gates on `min` /
`max`. Used by the newsletter pack to cap drafts at 700 words.

### Configuration Properties:
| Property | Type | Required | Description |
|---|---|---|---|
| `max` | `int` | No | Hard ceiling — fails if word count exceeds this. |
| `min` | `int` | No | Hard floor — fails if word count is below this. |

At least one of `max` / `min` should be set; both unset = always passes.

### Example Contract Usage:
```yaml
evaluators:
  - name: word_count
    mode: binary
    max: 700
```

---

## `last_paragraph_regex`

Like `regex`, but matches only against the LAST non-empty paragraph
(blank-line separated). Used by the newsletter pack to enforce a CTA verb
in the closing paragraph without an early-paragraph match satisfying the
gate.

### Configuration Properties:
| Property | Type | Required | Description |
|---|---|---|---|
| `pattern` | `string` | **Yes** | Regular expression to match against the last paragraph. |
| `case_sensitive` | `boolean` | No | Default `true`. |

### Example Contract Usage:
```yaml
evaluators:
  - name: last_paragraph_regex
    mode: binary
    case_sensitive: false
    pattern: '\b(reply|subscribe|share|join)\b'
```

---

## `exact_match`

Compares the whole response (reasoning stripped) to the test case's
`expected_output` after normalization. This is the name used by sample
datasets such as ben's `gsm8k-sample.yaml`; it is built in.

### Configuration Properties:
| Property | Type | Required | Description |
|---|---|---|---|
| `expected` | `string` | No | Fallback expected value when a case has no `expected_output`. |

Normalization (applies to both sides): trim; unwrap `**bold**`, backticks, quotes, `$`,
`\boxed{}`; drop a trailing period; remove thousands separators (`1,234` = `1234`); casefold;
collapse whitespace. If both sides parse as numbers they compare numerically (`6` = `6.0`).

**Dataset-case evaluator:** reads the case's `expected_output`. A case without one (and no
`expected` config) is not applicable: no result is recorded for it.

```yaml
evaluators:
  - name: exact_match
    mode: binary
tests:
  - id: q1
    input: "What is 3+5-2? Reply with only the number."
    expected_output: "6"
```

---

## `final_answer`

Like `exact_match`, but compares the **last** `Final answer: X` line of the response (also
matches `**Final answer:** X`, `> Final answer: X`, any case). Use it when the model reasons
before answering. No such line scores `0.0` (`no 'Final answer:' line found`).

Same config, normalization and applicability as `exact_match`. Instruct the model in the
prompt to end with `Final answer: <value>`.

---

## `code_tests`

> [!CAUTION]
> **Executes model output** on the machine running eva. Use only on trusted runs inside a
> sandbox (container / VM / throwaway user). Isolation is best-effort hygiene, not a security
> boundary: network and filesystem outside the temp dir are **not** blocked; CPU/RAM are not
> limited.

Extracts the **last** fenced code block for the language (a block tagged `python`/`py`/`python3`;
else the last untagged block; blocks inside `<think>` reasoning are ignored), appends the case's
tests, runs it, scores `1.0` (exit 0) or `0.0` with the reason (`no python code block found`,
`exit code 1: <stderr tail>`, `execution timeout after Ns`).

Execution: fresh temp dir (deleted after), `python -I` (isolated mode), minimal env (`PATH`,
`HOME`/`TMPDIR` = temp dir; no inherited secrets), stdin closed, process group killed on
timeout.

### Configuration Properties:
| Property | Type | Required | Description |
|---|---|---|---|
| `language` | `string` | No | Default `python`. Other languages: add a `CodeLanguage` to `CODE_LANGUAGES` in `core/evaluators/code_tests.py`. |
| `timeout` | `number` | No | Seconds, default `10`. `null` rejected. |
| `test_code` | `string` | No | Shared harness appended after each case's tests. |

### Test-case fields:
| Field | Type | Description |
|---|---|---|
| `tests` | `string` or `list[string]` | Test code (e.g. `assert` lines), joined by newlines, appended to the extracted code. A case with no `tests` (and no `test_code`) is not applicable: no result recorded. |

```yaml
evaluators:
  - name: code_tests
    timeout: 10
tests:
  - id: add
    input: "Write add(a, b) in Python."
    tests: |
      assert add(1, 2) == 3
      assert add(-1, 1) == 0
```

Related: `code_block_runs` only **parses** blocks (no execution); `code_test_passes` executes the
**first** python block with a config-level `test_code` (no per-case tests, `-c`, no temp dir).

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
