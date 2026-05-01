# core/evaluators/last_paragraph_regex.py
"""Tier-1 deterministic regex over the LAST paragraph only (T-0201, US-037).

A "paragraph" = block separated by blank lines (one or more). The newsletter
CTA contract uses this to assert the closing paragraph contains a CTA verb,
without a CTA verb earlier in the body counting against the gate.

For the whole-response variant, use the `regex` evaluator.
"""
from __future__ import annotations

import re

from core.models import Score


def _last_paragraph(text: str) -> str:
    """Return the last non-empty paragraph (blank-line separated). May be ''."""
    blocks = re.split(r"\n\s*\n", text.strip())
    for block in reversed(blocks):
        stripped = block.strip()
        if stripped:
            return stripped
    return ""


class LastParagraphRegexEvaluator:
    def __init__(self, pattern: str, case_sensitive: bool = True):
        flags = 0 if case_sensitive else re.IGNORECASE
        self.pattern = re.compile(pattern, flags)

    def run(self, response: str) -> Score:
        last = _last_paragraph(response)
        if not last:
            return Score(
                value=0.0,
                reason="empty response — no last paragraph to match",
            )
        if self.pattern.search(last):
            return Score(value=1.0)
        return Score(
            value=0.0,
            reason=(
                f"pattern '{self.pattern.pattern}' not found in "
                f"last paragraph"
            ),
        )

    _run = run  # deprecated alias; remove in v0.2.0
