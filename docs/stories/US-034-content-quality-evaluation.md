# US-034 — Content Quality Evaluators

**Associated Eva persona:** [Alex — AI Engineer](../personas.md)
**Shared base persona:** [Solo Developer](../../../../../.docs/personas/individuals/solo-developer.md)

## Story

As Alex, I want dedicated evaluators for bias, toxicity, summarization quality, prompt alignment,
and goal accuracy so that nuanced content quality issues are measured independently rather than
lumped into a generic safety check.

## Acceptance Criteria

- `bias` evaluator rates gender, racial, and political bias as a standalone signal independent of
  the general safety evaluator.
- `toxicity` evaluator provides dedicated toxicity scoring separate from other safety concerns.
- `summarization` evaluator checks faithfulness of the response to a source text when provided.
- `prompt_alignment` rates how well the response follows all instructions in the prompt.
- `goal_accuracy` measures whether the response achieves the intended goal or matches expected
  output.

## Related Plan

- [Metrics Expansion Plan](../plans/2026-03-28-observability-parity-plan.md)
