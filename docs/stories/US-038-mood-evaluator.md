# US-038 — Mood Evaluator

**ID:** EVA-NEW-MOOD
**Status:** v0.1 paper — Tier-1 (programmatic, no LLM)
**Author:** $USER
**Task:** T-0287, T-0295, T-0296
**Persona:** [Alex — AI Engineer](../personas.md) ·
[Solo Developer](../../../../../.docs/personas/individuals/solo-developer.md)

## User Goal

As Alex, I want a deterministic `mood` evaluator that flags whether an LLM
response is predominantly imperative, past-tense, passive, or first-person —
without invoking an LLM-judge — so that I can gate prose style (e.g.
"tutorial steps must be imperative", "marketing intro must not be past tense")
on the cheap, fast path of CI.

## Context

- Common in content quality gates: how-to instructions should be in
  imperative ("Open the file…"), product descriptions should be active
  voice (not passive), founder updates often forbid first-person fluff.
- Tier-1 only — uses verb-form / pronoun lookup tables + sentence-initial
  POS heuristics. No `nltk` / `spacy` dependency in v1.
- Evaluator config supplies a single `expected` mood. Score = 1.0 if the
  detected dominant mood equals `expected`, else 0.0.
- Sentence segmentation is regex-based on `.!?` plus newline / list-marker
  splits so bullet-step tutorials count each step as its own sentence.

## Acceptance Criteria

- `MoodEvaluator(expected="imperative").run(...)` returns `value=1.0` for a
  response where the majority of sentences begin with an imperative verb
  ("Open the file. Save it. Commit.").
- `MoodEvaluator(expected="past").run(...)` returns `value=1.0` for a
  response dominantly in past tense ("We shipped the feature. The team
  reviewed the PR.") and `value=0.0` for a present-tense response of
  equivalent length.
- `MoodEvaluator(expected="passive").run(...)` returns `value=1.0` when
  passive voice (`be`-form + past participle) dominates ("The file was
  saved. The commit was pushed.").
- `MoodEvaluator(expected="first_person").run(...)` returns `value=1.0` for
  responses where first-person pronouns (`I`, `we`, `my`, `our`) appear in
  most sentences.
- Score `reason` names the mismatch when failing (e.g. `"dominant mood past
  (n=4) != expected imperative (n=1)"`).
- Empty / whitespace-only response scores 0.0 with reason `"no <expected>
  sentences detected (scanned 1 sentences)"` (no crashes).
- Constructing with an unsupported `expected` raises `ValueError`.

## Implemented v0.1 (T-0295)

- `core/evaluators/mood.py` — `MoodEvaluator(expected)` + module-level
  `detect_mood_counts()` helper exposing the per-mood Counter.
- Verb-form lookup tables: `_PAST_IRREGULAR`, `_IMPERATIVE_LEAD`,
  `_FIRST_PERSON_*`, `_BE_FORMS`.
- Sentence splitter handles list markers (`-`, `*`, `1.`) so step-by-step
  prose scores correctly.

## Deferred (strict variants — follow-up tasks)

- POS-tagged variant using `spacy` for higher precision (adds dep — gated
  on dependency-trust review).
- `expected` as list (e.g. accept any of {imperative, infinitive}).
- Multi-language mood detection (v1 is English-only).

## Tests

### E2E

`tests/e2e/test_mood_evaluator.py` — one test per acceptance bullet.

## Dependencies

- Builds on: existing Tier-1 evaluator pattern (`word_count`, `regex`).
- Composes with: newsletter / meeting / tutorial contracts packs.
- Prereq for: tutorial-quality contract pack (planned).
