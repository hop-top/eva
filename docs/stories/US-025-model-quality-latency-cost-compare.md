# US-025 — Compare Model Quality, Latency, and Cost

**Associated Eva persona:** [Jordan — Compliance Officer](../personas.md)
**Shared base persona:** [Platform Engineer](../../../../../.docs/personas/individuals/platform-engineer.md)

## Story

As Jordan, I want to compare quality, latency, and estimated cost across model versions so that a
cheaper or newer model cannot be approved without evidence.

## Acceptance Criteria

- Eva stores explicit model identity for each invocation.
- Eva stores token usage and estimated cost when available.
- Eva can compare two models or targets on the same dataset.
- Comparison output includes quality metrics alongside latency and cost.
- Historical comparisons remain valid even if the target URL stays the same while the model changes.

## Related Plan

- [Observability Parity Plan](../plans/2026-03-28-observability-parity-plan.md)
