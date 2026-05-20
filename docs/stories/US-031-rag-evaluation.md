# US-031 — RAG Evaluation

**Associated Eva persona:** [Alex — AI Engineer](../personas.md)
**Shared base persona:** `individuals/solo-developer.md` (maintained in the shared hop-top personas library, outside this repo)

## Story

As Alex, I want to evaluate RAG pipeline quality using faithfulness, contextual relevancy,
precision, recall, answer relevancy, and RAGAS composite scores so that I can identify retrieval
and grounding failures before they reach users.

## Acceptance Criteria

- Test cases can include a `retrieval_context` field in dataset YAML.
- `faithfulness` evaluator checks response claims against retrieval context.
- `contextual_relevancy` evaluates relevance of retrieved context to the query.
- `contextual_precision` evaluates signal-to-noise ratio of retrieved context.
- `contextual_recall` evaluates coverage of relevant context across retrieved chunks.
- `answer_relevancy` rates how well the response answers the query.
- `ragas` composite evaluator runs all three context evaluators plus answer relevancy and returns an
  averaged score with per-component breakdown.
- All RAG evaluators degrade gracefully (fallback score) when `retrieval_context` is absent.

## Related Plan

- [Metrics Expansion Plan](../plans/2026-03-28-observability-parity-plan.md)
