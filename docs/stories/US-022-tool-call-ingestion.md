# US-022 — Ingest Tool-Call Events

**Associated Eva persona:** [Sam — Platform Engineer](../personas.md)
**Shared base persona:** [Platform Engineer](../../../../../.docs/personas/individuals/platform-engineer.md)

## Story

As Sam, I want Eva to ingest tool-call events from instrumented agents so that process failures can
be debugged instead of inferred from final output alone.

## Acceptance Criteria

- Eva accepts or records tool events linked to an invocation id.
- Each tool event includes tool name, args, result or error, status, and duration.
- Tool events preserve request or trace linkage for downstream debugging.
- Tool traces can be queried independently of final response text.
- Uninstrumented agents degrade gracefully without breaking normal Eva runs.

## Related Plan

- [Observability Parity Plan](../plans/2026-03-28-observability-parity-plan.md)
