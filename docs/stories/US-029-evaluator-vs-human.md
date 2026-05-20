# US-029 — Compare Automated Evaluators Against Human Labels

**Associated Eva persona:** [Riley — Evaluation Ops Lead](../personas.md)
**Shared base persona:** `individuals/platform-engineer.md` (maintained in the shared hop-top personas library, outside this repo)

## Story

As Riley, I want to compare automated evaluator scores against human labels so that weak or
misaligned evaluators can be identified and improved.

## Acceptance Criteria

- Eva can join annotations with automated evaluator results for the same invocation.
- Query output can highlight agreement and disagreement rates by evaluator.
- Evaluator-vs-human comparison can be sliced by dataset, model, or metadata tags.
- This workflow does not require exporting all results into a separate system first.

## Related Plan

- [Observability Parity Plan](../plans/2026-03-28-observability-parity-plan.md)
