# US-027 — Review Queue for Failed or Sampled Invocations

**Associated Eva persona:** [Riley — Evaluation Ops Lead](../personas.md)
**Shared base persona:** `individuals/platform-engineer.md` (maintained in the shared hop-top personas library, outside this repo)

## Story

As Riley, I want Eva to queue failed or sampled invocations for review so that humans can inspect
the highest-risk outputs first.

## Acceptance Criteria

- Eva can list failed or sampled invocations that have not yet been reviewed.
- Review queue entries link directly to invocation artifacts and evaluator results.
- Queue ordering supports at least failure-first and newest-first workflows.
- Review queue state survives process restarts.

## Related Plan

- [Observability Parity Plan](../plans/2026-03-28-observability-parity-plan.md)
