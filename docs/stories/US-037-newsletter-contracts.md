# US-037 — Newsletter Contracts Pack

**ID:** EVA-NEW-NEWSLETTER
**Status:** v0.1 shipped (Tier-1) — strict variants paper
**Author:** jadb
**Task:** T-0110, T-0201
**Persona:** [Alex — AI Engineer](../personas.md) ·
`individuals/solo-developer.md` (maintained in the shared hop-top personas library, outside this repo)

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

**Status (T-0201):** `eva pack` CLI surface still pending; v0.1 ships the four
contracts at `contracts/newsletter/` plus a `pack.yaml` manifest. Run each
file individually via `eva run --contract <file> --input draft.txt` until the
pack subcommand lands.

## Implemented v0.1 (T-0201)

- `newsletter-word-count-0.1` — `word_count` evaluator (max=700).
- `newsletter-no-hallucinations-0.1` — `regex` for `[ref:<id>]` marker
  presence (weakened from "every claim resolves to a ctxt object_id").
- `newsletter-style-0.1` — `regex` for tone-token allowlist (weakened from
  cosine-similarity vs. embedding).
- `newsletter-cta-presence-0.1` — new `last_paragraph_regex` evaluator.

Two new built-ins added to `BUILTIN_EVALUATOR_FACTORIES`: `word_count` and
`last_paragraph_regex`. Both Tier-1 deterministic.

## Deferred (strict variants — follow-up tasks)

- `style_match` Tier-3 plugin: cosine similarity vs. tone-profile embedding.
- `cite_coverage` Tier-3 plugin: `[ref:<id>]` markers must resolve to
  `metadata.source_object_ids` (ctxt object_id binding).
- LLM-judge fallback for unsourced factual claims via `hallucination`.
- `eva pack register / eva run --pack` CLI surface.

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
