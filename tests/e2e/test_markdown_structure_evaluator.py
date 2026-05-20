# tests/e2e/test_markdown_structure_evaluator.py
"""E2E tests: markdown_structure evaluator (T-0321, US-046).

One test case per acceptance bullet in docs/stories/US-046-markdown-structure-evaluator.md.
"""
from __future__ import annotations

from core.evaluators.markdown_structure import MarkdownStructureEvaluator
from core.models import Score


# AC1: required_h2 sections present -> pass.
def test_passes_when_required_h2_sections_present():
    body = "# Title\n\n## Overview\n\n## Usage\n\nsome text\n"
    ev = MarkdownStructureEvaluator(required_h2=["Overview", "Usage"])
    score = ev.run(body)
    assert isinstance(score, Score)
    assert score.value == 1.0


# AC2: required_h2 missing -> fail naming title.
def test_fails_on_missing_required_h2():
    body = "# Title\n\n## Overview\n"
    ev = MarkdownStructureEvaluator(required_h2=["Overview", "Usage"])
    score = ev.run(body)
    assert score.value == 0.0
    assert "Usage" in (score.reason or "")


# AC3: required_code_langs present -> pass.
def test_passes_when_required_code_langs_present():
    body = "```python\nprint(1)\n```\n\n```sh\necho hi\n```\n"
    ev = MarkdownStructureEvaluator(required_code_langs=["python", "sh"])
    score = ev.run(body)
    assert score.value == 1.0


# AC4: required code lang missing -> fail naming language.
def test_fails_when_required_code_lang_missing():
    body = "```python\nprint(1)\n```\n"
    ev = MarkdownStructureEvaluator(required_code_langs=["python", "json"])
    score = ev.run(body)
    assert score.value == 0.0
    assert "json" in (score.reason or "")


# AC5: disallow_broken_local_links and none broken -> pass.
def test_passes_when_no_broken_local_links():
    body = (
        "See [docs](./README.md) and [home](https://example.com) and "
        "[anchor](#section) and [mail](mailto:x@y.z)."
    )
    ev = MarkdownStructureEvaluator(disallow_broken_local_links=True)
    score = ev.run(body)
    assert score.value == 1.0


# AC6: broken local link present -> fail naming href.
def test_fails_on_broken_local_link():
    body = "Bad [link]() and another [t](../../../../broken)."
    ev = MarkdownStructureEvaluator(disallow_broken_local_links=True)
    score = ev.run(body)
    assert score.value == 0.0
    assert "broken local link" in (score.reason or "")


# AC7: degenerate empty-config -> pass any non-empty.
def test_degenerate_config_passes_non_empty():
    ev = MarkdownStructureEvaluator()
    score = ev.run("Just some text, no structure required.")
    assert score.value == 1.0


# AC8: empty response -> fail with "empty response".
def test_fails_on_empty_response():
    ev = MarkdownStructureEvaluator()
    score = ev.run("   \n  \n")
    assert score.value == 0.0
    assert "empty response" in (score.reason or "").lower()
