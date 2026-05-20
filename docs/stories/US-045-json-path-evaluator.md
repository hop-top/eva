# US-045 — json_path Evaluator

**Associated Eva persona:** [Alex — AI Engineer](../personas.md)
**Shared base persona:** [Solo Developer](../../../../../.docs/personas/individuals/solo-developer.md)
**Task:** T-0305, T-0318, T-0319

## Story

As Alex, I want a `json_path` evaluator that parses a JSON response, walks a configured path,
and compares the value at that path against an expected value with a chosen comparator
(`eq`, `neq`, `gt`, `lt`, `in`), so that structured-output contracts can gate on individual
fields without writing a regex per shape.

## Context

- v1 ships a **stdlib pointer-walk fallback** (no `jsonpath-ng` dep). Supports dotted paths
  (`a.b.c`) and bracket-indexed arrays (`items[0].name`). Documented limitation: no JSONPath
  wildcards (`$..foo`, `[*]`); story flags `jsonpath-ng` as a v2 dep ask.
- The response is expected to be JSON-parseable. If it isn't, evaluator fails with
  `invalid json` reason.
- Comparators in v1:
  - `eq` — value at path equals `expected` (Python `==`).
  - `neq` — value at path does NOT equal `expected`.
  - `gt` — value at path `> expected` (numeric only; non-numeric → fail).
  - `lt` — value at path `< expected` (numeric only).
  - `in` — value at path is one of the items in `expected` (a list).
- Missing path = fail, reason "path 'a.b.c' not found".

## Acceptance Criteria

- Evaluator parses a JSON response; non-JSON input fails with reason "invalid json".
- Evaluator with comparator `eq` passes when value at path equals expected; fails when not equal.
- Evaluator with comparator `neq` passes when value at path differs from expected.
- Evaluator with comparator `gt` passes on numeric `>`; fails on `<=` or non-numeric value at
  path (reason names the non-numeric type).
- Evaluator with comparator `lt` passes on numeric `<`; fails on `>=`.
- Evaluator with comparator `in` passes when value at path is a member of the `expected` list;
  fails when not.
- Evaluator fails with reason "path '...' not found" when the configured path doesn't resolve.
- Evaluator supports bracket-indexed arrays (`items[0].name`) and dotted keys (`a.b.c`).

## Tests

- `tests/e2e/test_json_path_evaluator.py` — one test case per acceptance bullet.

## Dependencies / Follow-ups

- v2 candidate: `jsonpath-ng` dep for full JSONPath syntax (wildcards, recursive descent,
  filter expressions). Would need pyproject change.
