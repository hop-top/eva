# core/evaluators/word_count.py
"""Tier-1 deterministic word-count gate (T-0201, US-037).

Configurable `min` and `max`. Whitespace-split (str.split() default —
collapses runs, strips). No language tokenisation; suitable for English
prose where 1 word ~= 1 whitespace-separated token. Newsletter contract
ships with `max: 700`.
"""
from __future__ import annotations

from core.models import Score


class WordCountEvaluator:
    def __init__(self, max: int | None = None, min: int | None = None):
        self.max = max
        self.min = min

    def run(self, response: str) -> Score:
        n = len(response.split())
        if self.min is not None and n < self.min:
            return Score(
                value=0.0,
                reason=f"word count {n} < {self.min} (min)",
            )
        if self.max is not None and n > self.max:
            return Score(
                value=0.0,
                reason=f"word count {n} > {self.max} (max)",
            )
        return Score(value=1.0)

    _run = run  # deprecated alias; remove in v0.2.0
