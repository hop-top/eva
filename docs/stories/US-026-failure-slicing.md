# US-026 — Slice Failures by Runtime Dimensions

**Associated Eva persona:** [Jordan — Compliance Officer](../personas.md)
**Shared base persona:** [Platform Engineer](../../../../../.docs/personas/individuals/platform-engineer.md)

## Story

As Jordan, I want to slice failures by evaluator, contract, model, and metadata tags so that
compliance issues can be isolated to the affected cohort quickly.

## Acceptance Criteria

- Eva exposes query or CLI filters for evaluator, contract, model, target, and metadata tags.
- Failure slices can be generated without direct SQL access.
- Queries can isolate a subset of invocations and show their associated artifacts and scores.
- The storage model supports indexed lookup rather than full JSON scanning for common filters.

## Related Plan

- [Observability Parity Plan](../plans/2026-03-28-observability-parity-plan.md)
