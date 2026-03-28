# US-024 — Inspect Historical Invocations

**Associated Eva persona:** [Jordan — Compliance Officer](../personas.md)
**Shared base persona:** [Platform Engineer](../../../../../.docs/personas/individuals/platform-engineer.md)

## Story

As Jordan, I want to inspect the exact request, response, contract version, and trace id for a
historical invocation so that audit reviews do not rely on screenshots or operator memory.

## Acceptance Criteria

- Historical invocations can be located by invocation id, request id, or trace id.
- Stored records show request artifact, response artifact, contract version, and evaluator results.
- The same invocation record is available after the original application logs have rotated away.
- Query output is suitable for audit and compliance review workflows.

## Related Plan

- [Observability Parity Plan](../plans/2026-03-28-observability-parity-plan.md)
