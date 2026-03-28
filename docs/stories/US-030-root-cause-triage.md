# US-030 — Root-Cause Triage Across Traces and Artifacts

**Associated Eva persona:** [Riley — Evaluation Ops Lead](../personas.md)
**Shared base persona:** [Platform Engineer](../../../../../.docs/personas/individuals/platform-engineer.md)

## Story

As Riley, I want to inspect tool traces, retrieved context, and evaluator results in one place so
that root-cause analysis is faster than reading scattered logs.

## Acceptance Criteria

- An invocation view can show response artifacts, tool events, evaluator results, and trace ids
  together.
- Retrieved context or grounding artifacts are linked when available.
- Triage can distinguish output failure from retrieval failure from tool-use failure.
- Operators can move from a failed evaluator to the supporting artifacts in one workflow.

## Related Plan

- [Observability Parity Plan](../plans/2026-03-28-observability-parity-plan.md)
