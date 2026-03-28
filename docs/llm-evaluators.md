# LLM-as-Judge Evaluators Reference

Tier 2 evaluators — use an LLM "judge" to score semantic qualities of agent responses.
Requires `EVA_JUDGE_MODEL` set in `.env`.

All return `Score(value: float)` in `[0.0, 1.0]`. All support `mode: binary | threshold | warn`.

---

## Configuration

```
EVA_JUDGE_MODEL=openai/gpt-4o-mini
OPENAI_API_KEY=sk-...
```

`EVA_JUDGE_MODEL` uses LiteLLM routing — supports any provider:

```
EVA_JUDGE_MODEL=anthropic/claude-3-haiku-20240307
EVA_JUDGE_MODEL=azure/gpt-4o
```

Cost note: each Tier 2 evaluator = 1 LLM call per test case. Use `mode: warn` during
development; switch to `threshold` or `binary` in CI.

---

## General Purpose

### `relevance`

Scores how directly the response addresses the input.

```yaml
evaluators:
  - name: relevance
    mode: threshold
    min_score: 0.7
```

---

### `hallucination`

Detects unsupported or fabricated claims. 1.0 = no hallucination, 0.0 = severely hallucinated.

```yaml
evaluators:
  - name: hallucination
    mode: binary
```

---

### `tone`

Checks the response matches a required communication style. Default: `professional`.

```yaml
evaluators:
  - name: tone
    mode: threshold
    min_score: 0.8
    # configure expected_tone via plugin init or YAML extension
```

---

### `task_completion`

Measures whether all aspects of the task in the prompt are fully addressed.

```yaml
evaluators:
  - name: task_completion
    mode: threshold
    min_score: 0.8
```

---

### `safety`

Scans for harmful, toxic, or policy-violating content. Hard binary gate — 0.0 on any violation.
Should always run in `binary` mode in production.

```yaml
evaluators:
  - name: safety
    mode: binary
```

---

### `bias`

Rates the degree of gender, racial, or political bias. 1.0 = no bias, 0.0 = severely biased.

```yaml
evaluators:
  - name: bias
    mode: threshold
    min_score: 0.8
```

---

### `toxicity`

Dedicated toxicity scorer — complements `safety` for fine-grained toxicity tracking.
1.0 = non-toxic, 0.0 = extremely toxic.

```yaml
evaluators:
  - name: toxicity
    mode: binary
```

---

### `summarization`

Rates faithfulness of a summary to its source text. When `source_text` is provided, checks
factual accuracy; otherwise rates general summary quality.

```yaml
evaluators:
  - name: summarization
    mode: threshold
    min_score: 0.75
    # pass source_text via dataset metadata or plugin init
```

---

### `prompt_alignment`

Measures how well the response follows all instructions given in the prompt.

```yaml
evaluators:
  - name: prompt_alignment
    mode: threshold
    min_score: 0.9
```

---

### `goal_accuracy`

Measures whether the agent achieved the intended goal or matched an expected output.
Reads `expected_output` from the test case or evaluator constructor.

```yaml
evaluators:
  - name: goal_accuracy
    mode: threshold
    min_score: 0.85
```

---

### `geval` (Custom Criteria)

Evaluate any criterion you define. Specify the `criteria` string; the judge rates 0.0–1.0.

```yaml
evaluators:
  - name: geval
    criteria: "The response must cite at least one source URL."
    mode: binary
```

Use multiple `geval` instances with different `name` aliases for independent criteria:

```yaml
evaluators:
  - name: cites_sources
    evaluator: geval
    criteria: "The response cites at least one source URL."
    mode: binary
  - name: no_jargon
    evaluator: geval
    criteria: "The response avoids technical jargon."
    mode: threshold
    min_score: 0.8
```

---

## RAG Evaluators

Require `retrieval_context` in the test case (dataset YAML field) or passed via run context.

### `faithfulness`

Checks all claims in the response are grounded in the retrieved context.
Falls back to general hallucination check when no retrieval context is available.

```yaml
evaluators:
  - name: faithfulness
    mode: binary
```

---

### `answer_relevancy`

Rates how directly and completely the response answers the query.

```yaml
evaluators:
  - name: answer_relevancy
    mode: threshold
    min_score: 0.7
```

---

### `contextual_relevancy`

Rates overall relevance of the retrieved context to the user query.

```yaml
evaluators:
  - name: contextual_relevancy
    mode: threshold
    min_score: 0.7
```

---

### `contextual_precision`

Rates how precisely the retrieved chunks are relevant (signal-to-noise of retrieval).

```yaml
evaluators:
  - name: contextual_precision
    mode: threshold
    min_score: 0.7
```

---

### `contextual_recall`

Rates whether the retrieved context covers the information needed for the expected output.
Reads `expected_output` from the test case.

```yaml
evaluators:
  - name: contextual_recall
    mode: threshold
    min_score: 0.7
```

---

### `ragas` (Composite)

Runs `faithfulness`, `contextual_relevancy`, and `answer_relevancy` and returns the average.
Metadata includes per-component scores.

```yaml
evaluators:
  - name: ragas
    mode: threshold
    min_score: 0.75
```

---

## Tool-Use / Agentic Evaluators

These evaluators read `tool_events` from the run context — a list of tool call records
emitted by the agent via Eva's `EventSink` API.

### `tool_correctness`

Rates whether the agent called the right tools for the task.
Reads `expected_tools: list[str]` from run context.

```yaml
evaluators:
  - name: tool_correctness
    mode: threshold
    min_score: 0.8
```

---

### `argument_correctness`

Rates whether the arguments passed to each tool call were correct.
Reads `expected_args: dict[tool_name, dict]` from run context.

```yaml
evaluators:
  - name: argument_correctness
    mode: threshold
    min_score: 0.8
```

---

### `tool_use`

High-level quality of tool usage: did the agent use tools appropriately and efficiently?

```yaml
evaluators:
  - name: tool_use
    mode: threshold
    min_score: 0.7
```

---

### `step_efficiency`

Penalizes unnecessary steps. Compares actual tool-call count against `planned_steps`.
Reads `planned_steps: list[str]` from the test case.

```yaml
evaluators:
  - name: step_efficiency
    mode: threshold
    min_score: 0.7
```

---

### `plan_adherence`

Rates how closely the agent's execution followed the planned steps.
Reads `planned_steps` from the test case.

```yaml
evaluators:
  - name: plan_adherence
    mode: threshold
    min_score: 0.8
```

---

### `plan_quality`

Rates the quality of the plan or approach described in the response (completeness,
feasibility, logical ordering).

```yaml
evaluators:
  - name: plan_quality
    mode: threshold
    min_score: 0.75
```

---

## Multi-Turn / Conversation Evaluators

These evaluators operate on `ConversationTestCase` datasets and read `conversation_history`
from the run context.

### `knowledge_retention`

Checks whether the agent correctly remembers and uses facts stated earlier in the conversation.

```yaml
evaluators:
  - name: knowledge_retention
    mode: threshold
    min_score: 0.8
```

---

### `conversation_completeness`

Rates whether all user needs expressed across the conversation were addressed by the end.

```yaml
evaluators:
  - name: conversation_completeness
    mode: threshold
    min_score: 0.8
```

---

### `turn_relevancy`

Per-turn relevance — does each response directly address the latest user message in context?

```yaml
evaluators:
  - name: turn_relevancy
    mode: threshold
    min_score: 0.7
```

---

### `turn_faithfulness`

Factual grounding across the full conversation history and any retrieval context.

```yaml
evaluators:
  - name: turn_faithfulness
    mode: threshold
    min_score: 0.8
```

---

### `role_adherence`

Rates how consistently the agent maintained the required persona throughout the conversation.
Default persona: `assistant`. Configure via evaluator constructor or plugin init.

```yaml
evaluators:
  - name: role_adherence
    mode: threshold
    min_score: 0.85
    # configure persona via plugin init
```

---

## Image / Multimodal Evaluators

These evaluators use a vision-capable LLM (e.g. `gpt-4o`, `claude-3-5-sonnet`).
Pass `image_url` (and optionally `original_image_url`) in the test case metadata.

> **Requirement:** `EVA_JUDGE_MODEL` must point to a vision-capable model.

### `text_to_image`

Rates how well a generated image matches the text prompt.

```yaml
evaluators:
  - name: text_to_image
    mode: threshold
    min_score: 0.7
```

---

### `image_editing`

Rates how well an edited image follows the editing instructions.
Reads `image_url` (result) and optionally `original_image_url` from context.

```yaml
evaluators:
  - name: image_editing
    mode: threshold
    min_score: 0.7
```

---

### `image_coherence`

Rates semantic alignment between an image and its accompanying text.

```yaml
evaluators:
  - name: image_coherence
    mode: threshold
    min_score: 0.7
```

---

### `image_helpfulness`

Rates whether the image contributes meaningful information for understanding the topic.

```yaml
evaluators:
  - name: image_helpfulness
    mode: threshold
    min_score: 0.6
```

---

### `image_reference`

Rates how accurately a text description describes what is actually in the image.

```yaml
evaluators:
  - name: image_reference
    mode: threshold
    min_score: 0.8
```

---

## Dataset Fields Reference

| Field | Evaluators that use it | Type |
|---|---|---|
| `retrieval_context` | `faithfulness`, `contextual_*`, `ragas`, `turn_faithfulness` | `string` |
| `planned_steps` | `step_efficiency`, `plan_adherence`, `plan_quality` | `list[string]` |
| `expected_output` | `goal_accuracy`, `contextual_recall` | `string` |
| `image_url` | all image evaluators | `string` (URL) |
| `original_image_url` | `image_editing` | `string` (URL) |

Add these fields to test cases in your dataset YAML:

```yaml
tests:
  - id: rag-test-1
    input: "What causes inflation?"
    expected_output: "Inflation is caused by..."
    retrieval_context: "Inflation is a general increase in prices..."
    metadata:
      image_url: "https://..."
```

---

## Combining Tiers

Recommended gate ordering for production contracts:

```yaml
evaluators:
  - name: json_schema_valid   # Tier 1 — structural gate (free)
    mode: binary
  - name: no_pii              # Tier 1 — compliance gate (free)
    mode: binary
  - name: safety              # Tier 2 — safety hard gate
    mode: binary
  - name: faithfulness        # Tier 2 — RAG quality
    mode: binary
  - name: relevance           # Tier 2 — semantic quality
    mode: threshold
    min_score: 0.7
```
