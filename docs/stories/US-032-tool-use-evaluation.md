# US-032 — Tool-Use and Agentic Evaluation

**Associated Eva persona:** [Alex — AI Engineer](../personas.md)
**Shared base persona:** `individuals/solo-developer.md` (maintained in the shared hop-top personas library, outside this repo)

## Story

As Alex, I want to evaluate tool usage quality and plan execution so that agentic failures are
caught before deployment.

## Acceptance Criteria

- Test cases can include `planned_steps` (list of expected steps) in dataset YAML.
- `tool_correctness` verifies the agent called the expected tools.
- `argument_correctness` verifies tool arguments match expectations.
- `tool_use` rates overall tool usage quality holistically.
- `step_efficiency` penalizes unnecessary steps relative to `planned_steps`.
- `plan_adherence` rates execution fidelity against a planned step sequence.
- `plan_quality` rates the quality of the plan itself independent of execution.
- `geval` accepts a custom criteria string for arbitrary LLM-judge evaluation.
- Tool events are passed to evaluators via the EventSink run context.

## Related Plan

- [Metrics Expansion Plan](../plans/2026-03-28-observability-parity-plan.md)
