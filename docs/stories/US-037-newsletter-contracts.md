# US-037 — Newsletter Contracts Pack

**ID:** EVA-NEW-NEWSLETTER
**Status:** paper
**Author:** jadb
**Task:** T-0110
**Persona:** [Alex — AI Engineer](../personas.md) ·
[Solo Developer](../../../../../.docs/personas/individuals/solo-developer.md)

## User Goal

As Alex, I want a registerable pack of four newsletter-domain contracts (word count, no
hallucinations, style match, CTA presence) so the showcase scenario 4a "weekly publish"
flow can quality-gate generated newsletter drafts via `eva run --contract` AND inline
as a `tlc flow` step gate — without each consumer redefining the rules.

## Context

- Showcase scenario 4a: transcript/event sources → newsletter draft → eva gate →
  founder-approval (tlc human step) → publish. Contracts pack centralises the gate.
- Tone profile: Content Director prompt style guide
  (`docs/style-guides/content-director.md`) — referenced; not copied.
- Source set: list of ctxt object_ids supplied at flow invocation
  (`metadata.source_object_ids: [...]`).
- Input shape: `{draft: str, metadata: {source_object_ids: [...], publish_date: str,
  audience: str}}`.
- Reuses eva built-ins: `regex`, `word_count`, `contains`, `hallucination` (LLM-judge),
  plus one Tier 3 plugin: `style_match` (cosine vs. tone-profile embedding).

## Contracts

### 1. `newsletter-word-count-0.1`

Cap 700 words. Hard fail above; warn 600-700.
Acceptance: pass 520w → exit 0; fail 850w → exit 1 `draft length 853 > 700 (max)`;
warn 660w → mode warn, exit 0.

### 2. `newsletter-no-hallucinations-0.1`

Every event/citation traces to `source_object_ids[]`. Extract `[ref:<id>]` markers +
named-entity sentences; check ref id ∈ source set; fallback LLM-judge `hallucination`
on residual.
Acceptance: pass when every marker matches a source id; fail on `[ref:obj_unknown]` →
`hallucinated source: obj_unknown not in metadata.source_object_ids`; fail on
unsourced factual claim ("Acme raised $50M") via LLM-judge.

### 3. `newsletter-style-0.1`

Match tone profile (Content Director style guide). Tier 3 plugin `style_match` embeds
draft + reference corpus; cosine similarity ≥ 0.78.
Acceptance: pass at 0.84; fail at 0.62 → `style mismatch: 0.62 < 0.78 (threshold); see
docs/style-guides/content-director.md`.

### 4. `newsletter-cta-presence-0.1`

Final paragraph regex against verb list (`subscribe|reply|share|join|read|register|book
|try|...`).
Acceptance: pass on "Reply with your take."; fail on descriptive-only final →
`CTA verb missing in final paragraph`.

## Pack Registration

`eva pack register newsletter@0.1`; combined gate via
`eva run --pack newsletter@0.1 --input draft.json` returns aggregate pass/fail.

## Tests

### E2E (planned)

- `tests/e2e/contracts/newsletter/word_count_test.go::TestNewsletter_WordCountPass`
- `tests/e2e/contracts/newsletter/word_count_test.go::TestNewsletter_WordCountFail`
- `tests/e2e/contracts/newsletter/no_hallucinations_test.go`
  ::`TestNewsletter_HallucinatedEventRejected`
- `tests/e2e/contracts/newsletter/style_test.go::TestNewsletter_StyleMatch`
- `tests/e2e/contracts/newsletter/style_test.go::TestNewsletter_StyleMismatch`
- `tests/e2e/contracts/newsletter/cta_test.go::TestNewsletter_CTAPresent`
- `tests/e2e/contracts/newsletter/cta_test.go::TestNewsletter_CTAMissing`
- `tests/e2e/contracts/newsletter/combined_test.go::TestNewsletter_CombinedGate`

### Unit (planned)

- `eva/contracts/newsletter/*_test.py` — per-contract evaluator tests.
- `eva/plugins/style_match_test.py` — embedding load, cosine threshold, edge cases.

## Dependencies

- Builds on: US-036-meeting-contracts (pack registration pattern).
- Composes with: tlc 025-flow-human-step, tlc 027-flow-datarefs.
- Prereq for: showcase scenario 4a end-to-end demo.
