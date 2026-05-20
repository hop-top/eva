# US-033 — Multi-Turn Conversation Evaluation

**Associated Eva persona:** [Alex — AI Engineer](../personas.md)
**Shared base persona:** `individuals/solo-developer.md` (maintained in the shared hop-top personas library, outside this repo)

## Story

As Alex, I want to evaluate multi-turn conversations so that issues like knowledge loss, incomplete
resolution, and persona drift are detected across conversation history.

## Acceptance Criteria

- Dataset supports `ConversationTestCase` with a list of turns (role + content pairs).
- `knowledge_retention` detects when the agent contradicts facts stated in earlier turns.
- `conversation_completeness` checks that all user needs raised across turns were addressed.
- `turn_relevancy` scores per-turn response relevance relative to the turn's user message.
- `turn_faithfulness` checks factual grounding across full conversation history and any retrieval
  context.
- `role_adherence` rates persona consistency across turns; expected persona is configurable.

## Related Plan

- [Metrics Expansion Plan](../plans/2026-03-28-observability-parity-plan.md)
