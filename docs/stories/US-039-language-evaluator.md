# US-039 — Language Evaluator

**ID:** EVA-NEW-LANGUAGE
**Status:** v0.1 paper — Tier-1 (stdlib-only language detection)
**Author:** $USER
**Task:** T-0288, T-0297, T-0298
**Persona:** [Alex — AI Engineer](../personas.md) ·
[Solo Developer](../../../../../.docs/personas/individuals/solo-developer.md)

## User Goal

As Alex, I want a `language` evaluator that asserts an LLM response is in
the expected natural language (e.g. fr / en / es) so I can catch "answered
in the wrong language" regressions in localised deployments — without
adding a heavy `langdetect` / `fasttext-lid` dependency to the v1 stack.

## Context

- Real failure mode: a French-tuned agent silently answers in English
  because the system prompt drift. Native unit tests should catch this.
- v1 uses a stdlib-only heuristic: Unicode-block script detection (CJK,
  Cyrillic, Arabic, Hebrew, Greek) plus common-word stoplists for English,
  French, Spanish, German, Italian, Portuguese.
- `langdetect` is NOT in pyproject; not adding it in v1 — flagged in
  agent summary if Alex wants the strict variant later.
- Supported ISO-639-1 codes: `en, fr, es, de, it, pt, ja, zh, ru, ar, he, el`.

## Acceptance Criteria

- `LanguageEvaluator(expected="en").run("The quick brown fox jumps over the
  lazy dog.")` → `value=1.0`.
- `LanguageEvaluator(expected="fr").run("Le chat est sur la table et le
  chien est dans le jardin.")` → `value=1.0`.
- `LanguageEvaluator(expected="es").run("El gato está sobre la mesa y el
  perro está en el jardín.")` → `value=1.0`.
- Wrong-language response fails: `LanguageEvaluator(expected="fr").run(
  "The cat is on the table.")` → `value=0.0` with reason naming both
  detected and expected.
- Non-Latin script: `LanguageEvaluator(expected="ja").run("これは日本語の
  テストです。")` → `value=1.0`.
- Mixed-language (50/50) input scores 0.0 with reason `"could not detect
  language ..."` (ambiguous → fail rather than guess).
- Empty / whitespace input scores 0.0 (no crashes).
- Constructing with an unsupported `expected` (e.g. `"klingon"`) raises
  `ValueError`.

## Implemented v0.1 (T-0297)

- `core/evaluators/language.py` — `LanguageEvaluator(expected)` and
  module-level `detect_language()` helper.
- `SUPPORTED_LANGUAGES` tuple exported for callers that want to validate
  upfront.
- Latin-script stoplists tuned for 1–3 sentence samples.

## Deferred (strict variants — follow-up tasks)

- Optional `langdetect` / `fasttext-lid` backend behind an `eva[langdetect]`
  extra for high-precision multi-paragraph detection.
- Per-paragraph language reporting (today the evaluator returns one verdict
  for the whole response).
- Additional stoplists (Dutch, Polish, Turkish, Vietnamese, …).

## Tests

### E2E

`tests/e2e/test_language_evaluator.py` — one test per acceptance bullet.

## Dependencies

- Builds on: existing Tier-1 evaluator pattern.
- Composes with: localised content packs (newsletter-fr, support-es).
- Prereq for: locale-aware showcase scenario (planned).
