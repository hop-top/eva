# US-042 — Citation / Grounding Evaluator

**Associated Eva persona:** [Alex — AI Engineer](../personas.md)
**Shared base persona:** [Solo Developer](../../../../../.docs/personas/individuals/solo-developer.md)
**Task:** T-0302, T-0312, T-0313

## Story

As Alex, I want a deterministic `citation` evaluator that confirms every citation marker in a
response resolves to a known source id (no LLM call required), so that newsletter, research, and
RAG outputs can be gated for "every claim is backed by a source" without paying for a judge model
on a known-shape signal.

## Context

- Complements the LLM-judge `hallucination` evaluator: where `hallucination` reasons about
  unsourced *factual claims*, `citation` is the cheaper structural check on *marker → source-id
  membership*.
- Marker shapes: `[ref:<id>]` (eva newsletter convention, US-037) and bare URL markers
  (`https://...`, `http://...`).
- Source set: passed via constructor as `allowed_sources: list[str]`. The caller (gateway or
  CLI) is responsible for plumbing it from `metadata.source_object_ids` or `sources`.
- v1 is **programmatic only** — no LLM fallback. The story explicitly defers
  semantic-equivalence checks to a later tier.

## Acceptance Criteria

- Evaluator passes (score 1.0) when the response contains zero citation markers AND
  `require_citation=False` (default).
- Evaluator passes when every `[ref:<id>]` marker in the response has its `<id>` present in the
  configured `allowed_sources` set.
- Evaluator passes when every bare URL marker in the response is present in the
  configured `allowed_sources` set (URL match is exact-string, not normalised).
- Evaluator fails (score 0.0) when at least one `[ref:<id>]` marker references an id not in
  `allowed_sources`; the reason names the offending id.
- Evaluator fails when at least one URL marker references a URL not in `allowed_sources`;
  the reason names the offending URL.
- Evaluator fails when `require_citation=True` and the response contains zero markers; the
  reason states "no citation markers found".
- Evaluator handles multiple markers of mixed types in one response; failure is reported on
  the first offending marker (deterministic order: scan left-to-right).
- Evaluator is pure-Python, no I/O, no LLM call — completes in O(n) over response length.

## Tests

- `tests/e2e/test_citation_evaluator.py` — one test case per acceptance bullet.

## Dependencies

- Builds on: US-037 (`[ref:<id>]` marker convention).
- Composes with: LLM-judge `hallucination` evaluator (cheaper pre-filter).
