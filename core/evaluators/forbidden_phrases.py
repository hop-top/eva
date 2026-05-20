# core/evaluators/forbidden_phrases.py
"""Tier-1 deterministic forbidden-phrases evaluator (US-040).

Case-insensitive multi-pattern matcher. Pass a banlist of literal phrases
(humanizer AI-tells, vendor banlists, brand-safety lists) and the response
fails if any of them are found.

Whole-word matching by default to avoid false positives on substrings of
unrelated words ("delve" ban shouldn't fire on "delvein"). Set
`whole_word=False` to allow substring matches.

Configuration:
    banlist: list[str]   — phrases to forbid. Empty list = always pass.
    whole_word: bool     — default True. When True, phrases match only on
                           word boundaries (Python `re.escape` + `\b`).
    case_sensitive: bool — default False.

Score:
    1.0 if no banned phrases are present, else 0.0 with a reason listing
    the first offending phrase.
"""
from __future__ import annotations

import re
from typing import Iterable

from core.models import Score


class ForbiddenPhrasesEvaluator:
    def __init__(
        self,
        banlist: Iterable[str] | None = None,
        *,
        whole_word: bool = True,
        case_sensitive: bool = False,
    ):
        self.banlist = [p for p in (banlist or []) if p]
        self.whole_word = whole_word
        self.case_sensitive = case_sensitive
        flags = 0 if case_sensitive else re.IGNORECASE
        self._patterns: list[tuple[str, re.Pattern[str]]] = []
        for phrase in self.banlist:
            esc = re.escape(phrase)
            if whole_word:
                # Use \b only on word-character boundaries. Phrases that
                # start/end with non-word chars get a relaxed boundary so
                # e.g. "—" or punctuation still matches.
                left = r"\b" if phrase[0].isalnum() or phrase[0] == "_" else ""
                right = r"\b" if phrase[-1].isalnum() or phrase[-1] == "_" else ""
                pattern = re.compile(f"{left}{esc}{right}", flags)
            else:
                pattern = re.compile(esc, flags)
            self._patterns.append((phrase, pattern))

    def run(self, response: str) -> Score:
        if not self._patterns:
            return Score(value=1.0)
        hits: list[str] = []
        for phrase, pat in self._patterns:
            if pat.search(response):
                hits.append(phrase)
        if hits:
            shown = ", ".join(repr(h) for h in hits[:3])
            extra = f" (+{len(hits) - 3} more)" if len(hits) > 3 else ""
            return Score(
                value=0.0,
                reason=f"forbidden phrase(s) present: {shown}{extra}",
            )
        return Score(value=1.0)

    _run = run  # deprecated alias; remove in v0.2.0
