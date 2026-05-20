# US-023 — Sampling, Redaction, and Retention Controls

**Associated Eva persona:** [Sam — Platform Engineer](../personas.md)
**Shared base persona:** `individuals/platform-engineer.md` (maintained in the shared hop-top personas library, outside this repo)

## Story

As Sam, I want configurable sampling, redaction, and retention on persisted artifacts so that
production observability does not create an uncontrolled data liability.

## Acceptance Criteria

- Operators can configure a capture sample rate for gateway invocations.
- Raw artifacts can be redacted before persistence.
- Retention limits can expire or purge stored artifacts on schedule.
- Oversized payloads are rejected, truncated, or externalized according to policy.
- Defaults are safe enough for production deployments.

## Related Plan

- [Observability Parity Plan](../plans/2026-03-28-observability-parity-plan.md)
