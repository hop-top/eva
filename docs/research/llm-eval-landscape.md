# LLM Evaluation Framework Landscape
*Research date: 2026-03-09*

## The Competitive Space

| Framework | Language | Best For | A2A/Gateway | Self-Hosted |
|-----------|----------|----------|-------------|-------------|
| DeepEval | Python | General LLM eval (pytest-style, 50+ metrics) | No | Yes |
| Langfuse | Python | Observability + evals + tracing | No | Yes |
| Comet Opik | Python | Comprehensive eval + RAG | No | Yes |
| Promptfoo | TypeScript | Prompt comparison + red teaming | No | Yes |
| RAGAS | Python | RAG-specific evaluation | No | Yes |
| Braintrust | Python | Prompt iteration + experiments | No | Cloud-primary |
| LM Eval Harness | Python | Research benchmarking | No | Yes |
| Giskard | Python | Security/bias testing | No | Yes |
| Langfuse | Python | Observability + eval | No | Yes |

**Critical gap**: None of them implement A2A contract enforcement as a runtime middleware gateway. That is Eva's differentiator.

## Eva's Differentiator

Eva = the only tool that sits in the request path at runtime, enforces behavioral contracts between agents, and self-heals via retry. All others are offline/async evaluation tools.

## Key Decisions for Eva

### CLI Framework: Typer (recommended)
- Built on Click, modern type-hint API, less boilerplate
- Production-ready for greenfield projects
- Auto-generated help and validation

### LLM Routing: LiteLLM (confirmed)
- 2,600+ models, 140+ providers
- Production-stable (v1.76.1-stable with 12hr load testing)
- OpenAI-compatible API format
- Unified interface with cost tracking and fallback

### Plugin System: `importlib.metadata` entry_points OR pluggy
- `importlib.metadata` = standard library, no extra deps
- `pluggy` = pytest's own plugin system, more powerful for hook-based architecture
- **Recommendation**: pluggy — gives hook lifecycle (before/after eval), better for evaluator plugins

### Async Task Queue: ARQ (recommended over Celery)
- Async-first, pairs naturally with FastAPI
- Redis only (simpler ops)
- Significantly faster for I/O-bound tasks
- Celery is heavier and designed for sync-first workloads

### Dataset Format: YAML (config) + JSONL (test data)
- YAML for eval definitions (human-editable, readable)
- JSONL for large datasets (streamable, line-by-line processing)
- JSON Schema for output validation

## LLM-as-Judge Best Practices

- Use binary or low-precision scoring (not 1-10 scales)
- Break complex criteria into separate evaluators
- Chain-of-Thought reasoning in judge prompts
- Low temperature for consistency
- Structured JSON outputs from judge
- Validate judges against manual labels before deploying
- Multi-agent judging (multiple personas) outperforms single judge on complex tasks

## Self-Healing / Retry Architecture

VIGIL pattern (Dec 2025 state of art):
- External reflective layer (outside agent's cognitive loop)
- Three phases: Observe → Diagnose → Remediate
- Detects silent failures (syntactically valid but semantically broken)
- Prompt adaptations + code patches as remediation

For Eva: implement as middleware interceptor that:
1. Evaluates response against registered evaluators
2. On failure: retry with hint injected into prompt
3. Max retries configurable, fallback to error response
