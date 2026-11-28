# core/evaluators/answer_match.py
"""Answer-match evaluators comparing a response to the case's ``expected_output``.

- ``exact_match``  — whole response (reasoning stripped), normalized
- ``final_answer`` — the LAST ``Final answer: X`` line, normalized

Normalization (both sides): strip, unwrap ``\\boxed{}`` / bold / backticks /
quotes / ``$``, drop a trailing period, remove thousands separators inside
numbers, casefold, collapse whitespace. If both sides parse as numbers they
compare numerically (``6`` == ``6.0``).

The expected value is the test case's ``expected_output`` (or the
evaluator's ``expected`` config as a fallback).
"""
from __future__ import annotations

import re

from core.chat_targets import split_reasoning
from core.models import Score

_FINAL = re.compile(
    r"^[ \t>*_`#-]*final[ \t]+answer[ \t*_`]*[:：][ \t*_`]*(.+?)[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_BOXED = re.compile(r"^\\boxed\{(.*)\}$", re.DOTALL)
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")
_WRAP = "*_`\"'$ \t\n"


def extract_final_answer(text: str) -> str | None:
    matches = _FINAL.findall(text)
    return matches[-1] if matches else None


def normalize_answer(s: str) -> str:
    s = s.strip().strip(_WRAP).rstrip(".").strip()
    m = _BOXED.match(s)
    if m:
        s = m.group(1).strip()
    s = s.strip(_WRAP).rstrip(".").strip()
    s = _THOUSANDS.sub("", s)
    return " ".join(s.casefold().split())


def _as_number(s: str) -> float | None:
    try:
        return float(s)
    except ValueError:
        return None


def answers_match(got: str, expected: str) -> bool:
    g, e = normalize_answer(got), normalize_answer(expected)
    if g == e:
        return True
    gn, en = _as_number(g), _as_number(e)
    return gn is not None and en is not None and gn == en


class AnswerMatchEvaluator:
    def __init__(self, extract: str = "whole", expected: str | None = None):
        if extract not in ("whole", "final_answer"):
            raise ValueError(f"extract must be 'whole' or 'final_answer'; got {extract!r}")
        self.extract = extract
        self.expected = expected

    def run(self, response: str) -> Score:
        return self.run_case(response, {}) or Score(
            value=0.0, reason="no expected value: set expected or use a dataset case"
        )

    def run_case(self, response: str, case: dict) -> Score | None:
        """Score one case; ``None`` = not applicable (no expected value)."""
        expected = case.get("expected_output")
        if expected is None:
            expected = self.expected
        if expected is None:
            return None
        answer, _ = split_reasoning(response)
        if self.extract == "final_answer":
            got = extract_final_answer(answer)
            if got is None:
                return Score(value=0.0, reason="no 'Final answer:' line found")
        else:
            got = answer
        if answers_match(got, str(expected)):
            return Score(value=1.0)
        shown = got if len(got) <= 120 else got[:117] + "..."
        return Score(
            value=0.0, reason=f"expected {str(expected)!r}, got {shown!r}"
        )


class ExactMatchEvaluator(AnswerMatchEvaluator):
    """Whole (reasoning-stripped) response vs ``expected_output``."""

    def __init__(self, expected: str | None = None):
        super().__init__(extract="whole", expected=expected)


class FinalAnswerEvaluator(AnswerMatchEvaluator):
    """Last ``Final answer: X`` line vs ``expected_output``."""

    def __init__(self, expected: str | None = None):
        super().__init__(extract="final_answer", expected=expected)
