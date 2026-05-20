# US-043 — code_block_runs Evaluator

**Associated Eva persona:** [Alex — AI Engineer](../personas.md)
**Shared base persona:** [Solo Developer](../../../../../.docs/personas/individuals/solo-developer.md)
**Task:** T-0303, T-0314, T-0315

## Story

As Alex, I want a `code_block_runs` evaluator that extracts fenced code blocks from a response
and asserts each one is syntactically parseable in its declared language, so that LLM-generated
code samples can be gated on "at least syntactically valid" without executing them.

## Context

- Distinct from `code_test_passes` (US-044): this is a parse-only check, no execution. Cheaper,
  no sandbox, and works for languages where running the snippet is undesirable.
- Markdown fence convention: ` ```lang\n...\n``` `. Languages are matched case-insensitively.
- Per-language parser strategy (v1):
  - `python` → `ast.parse` (stdlib).
  - `sh` / `bash` → `subprocess.run(["bash", "-n", ...])` syntax-check, 5s timeout.
  - `json` → `json.loads` (stdlib).
  - `yaml` → `yaml.safe_load` (pyyaml, already a dep).
  - Any other language → unsupported; per `unsupported_action` config flag the block is
    either skipped (default, pass-through) or fails the evaluator (strict mode).
- Deferred: `esprima` for JS, `sqlparse` for SQL — both would add deps; the story flags them
  as follow-ups.

## Acceptance Criteria

- Evaluator extracts all fenced code blocks from the response; blocks without a language tag are
  treated as `unsupported`.
- Evaluator passes when the response contains zero fenced code blocks AND
  `require_code_block=False` (default).
- Evaluator passes when every supported-language block parses successfully (python/sh/json/yaml).
- Evaluator fails when any python block has a `SyntaxError`; reason names the language and
  surfaces the first error message.
- Evaluator fails when any json block is malformed; reason names the language and surfaces the
  parse error.
- Evaluator fails when any bash block fails `bash -n`; reason includes the bash stderr snippet.
- Evaluator with `unsupported_action="fail"` fails on any block whose language is not in the
  supported set; reason names the unsupported language.
- Evaluator with `require_code_block=True` fails when zero blocks are found in the response.

## Tests

- `tests/e2e/test_code_block_runs_evaluator.py` — one test case per acceptance bullet.

## Dependencies / Follow-ups

- v2 considerations: `esprima` (JS), `sqlparse` (SQL) parsers. Would need pyproject changes.
