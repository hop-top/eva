# LLM-as-Judge Evaluators Reference

Tier 2 evaluators — use an LLM "judge" to score semantic qualities
of agent responses. Requires `EVA_JUDGE_MODEL` set in `.env`.

---

## Overview

| Evaluator       | What it measures                               | Mode           |
|-----------------|------------------------------------------------|----------------|
| `relevance`     | Response alignment with the input intent       | threshold      |
| `faithfulness`  | Factual grounding (no hallucination)           | binary/warn    |
| `tone`          | Professional / required tone match             | threshold/warn |
| `safety`        | Absence of harmful or disallowed content       | binary         |
| `completeness`  | All required points addressed                  | threshold      |

All return `Score(value: float)` in `[0.0, 1.0]`.

---

## `relevance`

Scores how well the agent's response addresses the input.
Judge prompt asks: "Does this response answer the question?"

```yaml
# contract YAML snippet
evaluators:
  - name: relevance
    mode: threshold
    min_score: 0.7
```

| Property    | Type    | Default | Description                          |
|-------------|---------|---------|--------------------------------------|
| `mode`      | string  | —       | `threshold` recommended.             |
| `min_score` | float   | `1.0`   | Minimum to pass; 0.7 typical.        |

---

## `faithfulness`

Detects hallucination — checks response against provided context/facts.
Returns 0.0 if unsupported claims found.

```yaml
evaluators:
  - name: faithfulness
    mode: binary
```

Use `warn` to collect data without blocking:

```yaml
evaluators:
  - name: faithfulness
    mode: warn
```

---

## `tone`

Checks response matches required communication style
(professional, friendly, concise, etc.).

```yaml
evaluators:
  - name: tone
    mode: threshold
    min_score: 0.8
    # tone config set via plugin init or eva.yaml extension
```

---

## `safety`

Scans for harmful, toxic, or policy-violating content.
Hard binary gate — 0.0 if any violation detected.

```yaml
evaluators:
  - name: safety
    mode: binary
```

Should always run in `binary` mode — never `warn` in production.

---

## `completeness`

Measures whether the response addresses all required aspects
of the input (e.g., all sub-questions answered).

```yaml
evaluators:
  - name: completeness
    mode: threshold
    min_score: 0.75
```

---

## Configuration

### Required env

```
EVA_JUDGE_MODEL=openai/gpt-4o-mini
OPENAI_API_KEY=sk-...
```

`EVA_JUDGE_MODEL` uses LiteLLM routing — supports any provider:

```
EVA_JUDGE_MODEL=anthropic/claude-3-haiku-20240307
EVA_JUDGE_MODEL=azure/gpt-4o
```

### Cost considerations

- Each Tier 2 evaluator = 1+ LLM call per test case.
- Use `mode: warn` during development to avoid gate failures.
- Batch-run Tier 2 separately from Tier 1 to control cost.

---

## Combining tiers

Best practice: gate on Tier 1 first (fast, free), add Tier 2 for semantic:

```yaml
evaluators:
  - name: json_schema_valid   # Tier 1 — structural gate
    mode: binary
  - name: no_pii              # Tier 1 — compliance gate
    mode: binary
  - name: relevance           # Tier 2 — semantic quality
    mode: threshold
    min_score: 0.7
  - name: safety              # Tier 2 — safety gate
    mode: binary
```
