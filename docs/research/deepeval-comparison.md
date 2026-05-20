# DeepEval vs Eva: Feature Comparison
*Research date: 2026-03-28*
*Source: https://github.com/confident-ai/deepeval*

---

## Metrics / Evaluators

### General Purpose

| Evaluator | DeepEval | Eva |
|-----------|----------|-----|
| Relevance | ✅ | ✅ `relevance` |
| Hallucination | ✅ | ✅ `hallucination` |
| Tone | ✅ | ✅ `tone` |
| Task Completion | ✅ | ✅ `task_completion` |
| Safety | ✅ | ✅ `safety` |
| Bias | ✅ | ✅ `bias` |
| Toxicity | ✅ | ✅ `toxicity` |
| Summarization | ✅ | ✅ `summarization` |
| Prompt Alignment | ✅ | ✅ `prompt_alignment` |
| Goal Accuracy | ✅ | ✅ `goal_accuracy` |
| Custom Criteria (G-Eval) | ✅ | ✅ `geval` |

### RAG / Retrieval

| Evaluator | DeepEval | Eva |
|-----------|----------|-----|
| Faithfulness | ✅ | ✅ `faithfulness` |
| Answer Relevancy | ✅ | ✅ `answer_relevancy` |
| Contextual Relevancy | ✅ | ✅ `contextual_relevancy` |
| Contextual Precision | ✅ | ✅ `contextual_precision` |
| Contextual Recall | ✅ | ✅ `contextual_recall` |
| RAGAS Composite | ✅ | ✅ `ragas` |

### Tool-Use / Agentic

| Evaluator | DeepEval | Eva |
|-----------|----------|-----|
| Tool Correctness | ✅ | ✅ `tool_correctness` |
| Argument Correctness | ✅ | ✅ `argument_correctness` |
| Tool Use (quality) | ✅ | ✅ `tool_use` |
| Step Efficiency | ✅ | ✅ `step_efficiency` |
| Plan Adherence | ✅ | ✅ `plan_adherence` |
| Plan Quality | ✅ | ✅ `plan_quality` |

### Multi-Turn Conversation

| Evaluator | DeepEval | Eva |
|-----------|----------|-----|
| Knowledge Retention | ✅ | ✅ `knowledge_retention` |
| Conversation Completeness | ✅ | ✅ `conversation_completeness` |
| Turn Relevancy | ✅ | ✅ `turn_relevancy` |
| Turn Faithfulness | ✅ | ✅ `turn_faithfulness` |
| Role Adherence | ✅ | ✅ `role_adherence` |

### Image / Multimodal

| Evaluator | DeepEval | Eva |
|-----------|----------|-----|
| Text-to-Image | ✅ | ✅ `text_to_image` |
| Image Editing | ✅ | ✅ `image_editing` |
| Image Coherence | ✅ | ✅ `image_coherence` |
| Image Helpfulness | ✅ | ✅ `image_helpfulness` |
| Image Reference | ✅ | ✅ `image_reference` |

### Deterministic / Structural

| Evaluator | DeepEval | Eva |
|-----------|----------|-----|
| JSON Schema | ✅ implicit | ✅ `json_schema_valid` (Tier 1) |
| Substring Match | ✅ implicit | ✅ `contains` (Tier 1) |
| Regex | ✅ implicit | ✅ `regex` (Tier 1) |
| No PII | ✅ | ✅ `no_pii` (Tier 1) |

**Metric verdict: full parity.** Eva now covers every evaluator category DeepEval documents.

---

## Dataset / Test Case Model

| Aspect | DeepEval | Eva |
|--------|----------|-----|
| Format | Python objects + YAML | YAML + JSONL |
| Metadata model | Open dict | Standardized fields (`retrieval_context`, `planned_steps`, `image_url`, etc.) |
| Conversation support | `ConversationTestCase` with `messages` | `ConversationTestCase` with `turns` |
| Field validation | Schema-based | Contract-first + field-level validation |
| JSONL | ✅ | ✅ |

---

## Integrations

| Aspect | DeepEval | Eva |
|--------|----------|-----|
| CI/CD | ✅ pytest-native | ✅ CLI-native (`eva run`) |
| Exit codes | ✅ | ✅ |
| Production gateway | Via Confident AI cloud | ✅ Native `eva serve` sidecar |
| OTEL / tracing | Via Confident AI cloud | ✅ Native, vendor-agnostic |
| Framework integrations | OpenAI, LangChain, CrewAI, LlamaIndex (direct) | Any (plugin pattern) |
| Multi-agent OASF / A2A / MCP | ❌ | ✅ Phase 4 roadmap |

---

## Observability / Storage

| Aspect | DeepEval | Eva |
|--------|----------|-----|
| Local storage | ❌ cloud-only | ✅ SQLite default |
| Self-hosted DB | ❌ | ✅ PostgreSQL adapter (planned) |
| Tracing backend | Confident AI proprietary | ✅ OTEL — Jaeger, Datadog, Tempo, etc. |
| Data ownership | Cloud-managed | User-controlled |
| Query surface | Web dashboard | SQL + OTEL tooling |

---

## Human Annotation / Review

| Aspect | DeepEval | Eva |
|--------|----------|-----|
| Review queue UI | ✅ Confident AI web | ✅ `eva review queue` CLI |
| Annotation storage | ✅ Cloud | ✅ SQLite (Annotation model) |
| Human vs evaluator comparison | ✅ Cloud dashboard | ⚠️ data model exists, no UI |
| Corrected output storage | ✅ | ✅ |

---

## Synthetic Data Generation

| Aspect | DeepEval | Eva |
|--------|----------|-----|
| Single-turn synthesis | ✅ built-in | ❌ |
| Multi-turn synthesis | ✅ built-in | ❌ |
| Prompt optimization | ✅ built-in | ❌ |

This is the largest functional gap. DeepEval can generate test datasets from docs or prompts; Eva requires manual dataset authoring.

---

## Standard Benchmarks

| Aspect | DeepEval | Eva |
|--------|----------|-----|
| MMLU | ✅ | ❌ |
| HellaSwag | ✅ | ❌ |
| GSM8K | ✅ | ❌ |
| Custom benchmark framework | ✅ | ❌ |

---

## Eva-Specific Strengths (no DeepEval equivalent)

**Contract-as-code enforcement**
YAML contracts define both evaluation criteria and request validation. Contracts are diff-able, versionable, and reviewable in PRs. DeepEval has no equivalent primitive — test suites are code, not declarations.

**Production gateway sidecar**
`eva serve` enforces contracts inline on every request. DeepEval has no production enforcement mode; evaluation is always offline. Confident AI cloud provides monitoring but not inline blocking.

**Retry + self-healing**
Eva can inject correction hints and retry the agent on contract violations. DeepEval evaluates but never intervenes.

**Deterministic Tier 1 (zero LLM cost)**
Structural validators (`contains`, `regex`, `json_schema`, `no_pii`) run free with no LLM calls. DeepEval doesn't make this distinction explicit.

**Full local operation**
Zero cloud dependency. Sensitive data never leaves the machine. DeepEval's collaboration and monitoring features require Confident AI.

**OTEL-native, vendor-agnostic tracing**
Spans export to any OTEL backend. DeepEval's observability is locked to Confident AI.

**Multi-agent ecosystem alignment**
AGNTCY/OASF, A2A, MCP protocol support on roadmap. DeepEval doesn't target multi-agent orchestration.

---

## Remaining Gaps (DeepEval ahead)

| Gap | Priority | Notes |
|-----|----------|-------|
| Synthetic dataset generation | High | Largest workflow gap; users must manually author all test cases |
| Prompt optimization | Medium | Auto-tuning from eval results would accelerate iteration |
| Standard benchmarks (MMLU, etc.) | Medium | Needed for model comparison workflows |
| Human review web UI | Low | CLI annotation exists; web UI would improve ops workflows |
| Direct framework integrations | Low | Plugin pattern covers this; just more setup |

---

## Positioning Summary

> **DeepEval** = *"How do I test and iterate on my agent during development?"*
> **Eva** = *"How do I enforce what my agent can and cannot do in production?"*

They are complementary, not directly competitive. A complete stack could use DeepEval for development iteration and synthetic data, and Eva for production enforcement, observability, and contract governance.

The three highest-value gaps to close for Eva to cover the full developer lifecycle:
1. Synthetic dataset generation
2. Standard benchmark harness
3. Prompt optimization loop
