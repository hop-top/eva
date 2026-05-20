# US-047 — sentence_count / paragraph_count Evaluator

**Associated Eva persona:** [Alex — AI Engineer](../personas.md)
**Shared base persona:** [Solo Developer](../../../../../.docs/personas/individuals/solo-developer.md)
**Task:** T-0307, T-0322, T-0323

## Story

As Alex, I want a structural counter evaluator that gates responses on sentence count and/or
paragraph count, so I can enforce "summary must be 3-5 sentences" or "answer must be a single
paragraph" without resorting to regex magic per contract.

## Context

- One class, two modes via `mode: "sentence" | "paragraph"`. Both report a single integer
  count compared to `min`/`max` bounds (same semantics as `word_count`).
- Sentence segmentation (v1):
  - Stdlib regex split on `[.?!]+\s+` then trim. Abbreviation handling: a small allowlist
    `{"Mr.", "Mrs.", "Ms.", "Dr.", "Prof.", "Sr.", "Jr.", "St.", "vs.", "e.g.", "i.e.",
    "etc."}` is masked before the split.
  - Bullet list items (lines starting with `-`, `*`, `+`, or `1.`) count as **one sentence
    each** regardless of terminal punctuation.
- Paragraph segmentation: blocks separated by one or more blank lines (re-uses the convention
  from `last_paragraph_regex`).
- Blockquote handling (`> ...` lines): treated as a single paragraph when contiguous;
  individual sentences inside are still counted.

## Acceptance Criteria

- Evaluator with `mode="sentence"` passes when sentence count is within `[min, max]` inclusive.
- Evaluator with `mode="sentence"` fails when count < min OR > max; reason names the count and
  the violated bound.
- Evaluator handles common abbreviations (`Dr.`, `Mr.`, `e.g.`) — "Dr. Smith said hi." counts
  as 1 sentence, not 2.
- Evaluator counts bullet list items as one sentence each, regardless of terminal punctuation.
- Evaluator with `mode="paragraph"` passes when paragraph count is within `[min, max]`.
- Evaluator with `mode="paragraph"` fails when count is out of bounds; reason names the count.
- Evaluator treats blockquote groups (`> ...` lines) as a single paragraph.
- Evaluator with neither `min` nor `max` set passes any non-empty response (degenerate-pass).

## Tests

- `tests/e2e/test_sentence_paragraph_count_evaluator.py` — one test case per acceptance bullet.

## Dependencies / Follow-ups

- v2: full sentence tokeniser via `nltk` or `spacy` would handle edge cases (quotes, parens,
  ellipses) better. Story flags as follow-up, no dep added in v1.
