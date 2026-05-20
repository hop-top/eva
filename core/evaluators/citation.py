# core/evaluators/citation.py
"""Tier-2 deterministic citation / grounding evaluator (T-0312, US-042).

Extract `[ref:<id>]` markers and bare URL markers from a response and assert
every marker resolves to a member of the configured `allowed_sources` set.

Pure-Python, no I/O, no LLM call — O(n) over response length. Complements
the LLM-judge `hallucination` evaluator: cheaper structural pre-filter.
"""
from __future__ import annotations

import re
from typing import Iterable

from core.models import Score


_REF_PATTERN = re.compile(r"\[ref:([^\]\s]+)\]")
_URL_PATTERN = re.compile(r"https?://[^\s\)\]]+")


class CitationEvaluator:
    def __init__(
        self,
        allowed_sources: Iterable[str] | None = None,
        require_citation: bool = False,
    ):
        self.allowed_sources = set(allowed_sources or [])
        self.require_citation = require_citation

    def run(self, response: str) -> Score:
        # Find every marker, preserving left-to-right scan order so the
        # *first* offender is reported deterministically. Capture the
        # match start offset DURING the regex scan — using
        # ``response.find`` after the fact collapses duplicate markers
        # to the same offset and breaks left-to-right ordering.
        markers: list[tuple[int, str, str]] = []  # (start, kind, value)
        for m in _REF_PATTERN.finditer(response):
            markers.append((m.start(), "ref", m.group(1)))
        for m in _URL_PATTERN.finditer(response):
            markers.append((m.start(), "url", m.group(0)))
        markers.sort(key=lambda x: x[0])

        if not markers:
            if self.require_citation:
                return Score(
                    value=0.0,
                    reason="no citation markers found",
                )
            return Score(value=1.0)

        for _start, kind, value in markers:
            if value not in self.allowed_sources:
                label = "source id" if kind == "ref" else "url"
                return Score(
                    value=0.0,
                    reason=(
                        f"unsourced {label}: {value} not in "
                        f"allowed_sources"
                    ),
                )
        return Score(value=1.0)

    _run = run  # deprecated alias; remove in v0.2.0
