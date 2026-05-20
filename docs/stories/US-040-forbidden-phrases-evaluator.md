# US-040 — Forbidden Phrases Evaluator

**ID:** EVA-NEW-FORBIDDEN-PHRASES
**Status:** v0.1 paper — Tier-1 (deterministic banlist matcher)
**Author:** $USER
**Task:** T-0289, T-0299, T-0300
**Persona:** [Alex — AI Engineer](../personas.md) ·
[Solo Developer](../../../../../.docs/personas/individuals/solo-developer.md)

## User Goal

As Alex, I want a `forbidden_phrases` evaluator that fails any response
containing a phrase from a configurable banlist (vendor-supplied humanizer
AI-tells, brand-safety lists, competitor names) — case-insensitive,
whole-word by default — so I can ship per-contract prose filters without
hand-rolling a regex each time.

## Context

- Repeat use case: "ban every 'delve', 'tapestry', 'in the realm of'
  humanizer-tell" or "never mention competitor X by name in support
  responses". A regex evaluator works but every contract has to escape
  patterns manually.
- v1 takes a literal-phrase banlist. Phrases are escaped with
  `re.escape`; whole-word boundaries (`\b`) are added by default to avoid
  false positives (banning `cat` shouldn't fire on `concatenate`).
- Optional flags: `whole_word=False` for substring matches,
  `case_sensitive=True` for brand-name banlists.

## Acceptance Criteria

- `ForbiddenPhrasesEvaluator(banlist=["delve", "tapestry"]).run("We delve
  into the data.")` → `value=0.0`, reason names `'delve'`.
- Same evaluator on a clean response ("We explore the data.") → `value=1.0`.
- Empty banlist always passes:
  `ForbiddenPhrasesEvaluator(banlist=[]).run(anything)` → `value=1.0`.
- Case-insensitive by default: `ForbiddenPhrasesEvaluator(banlist=["DELVE"])
  .run("we delve here")` → `value=0.0`.
- Whole-word default does NOT fire on substring:
  `ForbiddenPhrasesEvaluator(banlist=["cat"]).run("concatenate strings")` →
  `value=1.0`.
- With `whole_word=False`, substring DOES fire:
  `ForbiddenPhrasesEvaluator(banlist=["cat"], whole_word=False).run(
  "concatenate")` → `value=0.0`.
- Multi-word phrase: `ForbiddenPhrasesEvaluator(banlist=["in the realm
  of"]).run("In the realm of AI, ...")` → `value=0.0`.
- Multiple hits are summarised in `reason`: top 3 shown, `+N more` suffix
  beyond that.

## Implemented v0.1 (T-0299)

- `core/evaluators/forbidden_phrases.py` — `ForbiddenPhrasesEvaluator(
  banlist, *, whole_word=True, case_sensitive=False)`.
- Patterns are compiled at construction (`re.compile` once per phrase).

## Deferred (strict variants — follow-up tasks)

- Categorised banlist (e.g. `{"ai_tells": [...], "competitors": [...]}`)
  so the failure reason can name the category.
- Regex-pattern banlist mode (today everything is literal-escaped).
- Severity per phrase (warn vs fail).

## Tests

### E2E

`tests/e2e/test_forbidden_phrases_evaluator.py` — one test per acceptance
bullet.

## Dependencies

- Builds on: `regex_match` Tier-1 pattern.
- Composes with: humanizer-skill output gate, newsletter pack (banlist of
  cliché openers).
- Prereq for: humanizer skill ship-gate (planned).
