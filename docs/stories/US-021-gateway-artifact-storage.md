# US-021 — Persist Gateway Request/Response Artifacts

**Associated Eva persona:** [Sam — Platform Engineer](../personas.md)
**Shared base persona:** [Platform Engineer](../../../../../.docs/personas/individuals/platform-engineer.md)

## Story

As Sam, I want Eva to persist raw request/response artifacts for gateway traffic so that operators
can reconstruct exactly what happened during an incident.

## Acceptance Criteria

- Every gateway invocation stores a stable invocation id.
- The original request body is persisted or durably referenced.
- The final response body is persisted or durably referenced on both pass and fail paths.
- Stored artifacts are queryable by request id, trace id, contract, and target.
- Operators can inspect a historical invocation without relying on application logs.

## Related Plan

- [Observability Parity Plan](../plans/2026-03-28-observability-parity-plan.md)
