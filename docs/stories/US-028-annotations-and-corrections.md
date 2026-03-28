# US-028 — Store Annotations and Corrected Outputs

**Associated Eva persona:** [Riley — Evaluation Ops Lead](../personas.md)
**Shared base persona:** [Platform Engineer](../../../../../.docs/personas/individuals/platform-engineer.md)

## Story

As Riley, I want to attach annotations and corrected outputs to an invocation so that Eva becomes
the system of record for both automated and human evals.

## Acceptance Criteria

- A reviewer can attach a label, score, and notes to an invocation.
- A reviewer can attach or reference a corrected output artifact.
- Annotations are queryable alongside automated evaluator results.
- Multiple annotations per invocation are supported without data loss.

## Related Plan

- [Observability Parity Plan](../plans/2026-03-28-observability-parity-plan.md)
