# US-046 — markdown_structure Evaluator

**Associated Eva persona:** [Alex — AI Engineer](../personas.md)
**Shared base persona:** [Solo Developer](../../../../../.docs/personas/individuals/solo-developer.md)
**Task:** T-0306, T-0320, T-0321

## Story

As Alex, I want a `markdown_structure` evaluator that asserts the response is well-formed
markdown with specific required structural elements (H2 sections, fenced code blocks of given
languages, no broken local links), so that documentation/README-style outputs can be gated
without writing a brittle regex per requirement.

## Context

- v1 uses a **stdlib regex scanner** rather than a markdown parser dep (no `markdown-it-py`
  or `mistune`). Documented limitation: ignores HTML-block edge cases and tab-indented code
  fences. Story flags `markdown-it-py` as a v2 dep candidate if richer parsing is needed.
- Scanner extracts:
  - ATX headings (`# … ######`) with depth & text.
  - Fenced code blocks (` ``` ... ``` `) with language tag.
  - Local links — markdown `[text](url)` where `url` does not start with `http://`, `https://`,
    `mailto:`, or `#`. v1 does not perform filesystem existence checks; "broken local link"
    means **empty href** or `(./missing)` style with no extension that looks like a path
    typo — operationalised as "starts with `./` or `../` and contains `..` or empty target".
    Documented edge case; reviewers should not over-rely on link checking.
- Config fields: `required_h2: list[str]`, `required_code_langs: list[str]`,
  `disallow_broken_local_links: bool`.

## Acceptance Criteria

- Evaluator passes when all `required_h2` section titles appear as `## <title>` headings in the
  response (exact match on stripped heading text).
- Evaluator fails when a `required_h2` title is missing; reason names the missing title.
- Evaluator passes when every language in `required_code_langs` has at least one matching
  fenced code block (e.g. `required_code_langs=["python"]` needs at least one ` ```python ` block).
- Evaluator fails when a required code language is absent; reason names the missing language.
- Evaluator passes when `disallow_broken_local_links=True` and no broken local links exist.
- Evaluator fails with reason naming the offending href when `disallow_broken_local_links=True`
  and a broken local link pattern is found (empty target or `./../` malformed).
- Evaluator with empty config (`required_h2=[]`, `required_code_langs=[]`,
  `disallow_broken_local_links=False`) passes any non-empty response — degenerate-pass mode.
- Evaluator fails on empty response with reason "empty response".

## Tests

- `tests/e2e/test_markdown_structure_evaluator.py` — one test case per acceptance bullet.

## Dependencies / Follow-ups

- v2 candidate: `markdown-it-py` for proper CommonMark parsing. Would need pyproject change.
- Filesystem-existence check for local links deferred.
