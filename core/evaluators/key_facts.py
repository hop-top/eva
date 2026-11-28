# core/evaluators/key_facts.py
"""Per-case key-fact evaluator: required facts, forbidden strings, coverage.

Facts live on the case under ``metadata.key_facts``::

    metadata:
      key_facts:
        required:                 # each item is one fact
          - "Paris"               # a bare string = one accepted variant
          - ["1889", "year 1889"] # a list = accepted variants (any counts)
        forbidden: ["Berlin"]     # optional; any hit forces the score to 0

Score = facts found / total facts. A fact is found when ANY of its variants
occurs as a substring of the response. A forbidden string present forces 0.0.
``threshold`` (default 1.0 = every fact) is the coverage that passes: at or
above it the score is 1.0, below it the raw coverage. Matching is
case-insensitive and whitespace-normalised by default.

Without a case (contract mode) facts come from the ``required`` / ``forbidden``
config instead; with neither, ``run`` scores 0.0.
"""
from __future__ import annotations

from typing import Any

from core.chat_targets import split_reasoning
from core.evaluators._field import extract_text_field
from core.models import Score

_NAME = "key_facts"


class FactsError(ValueError):
    pass


def _parse_required(raw: Any) -> list[list[str]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise FactsError("required must be a list")
    facts: list[list[str]] = []
    for i, item in enumerate(raw):
        variants = [item] if isinstance(item, str) else item
        if (
            not isinstance(variants, list)
            or not variants
            or not all(isinstance(v, str) and v.strip() for v in variants)
        ):
            raise FactsError(
                f"required[{i}] must be a non-empty string or a non-empty "
                "list of non-empty strings"
            )
        facts.append(list(variants))
    return facts


def _parse_forbidden(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list) or not all(
        isinstance(v, str) and v.strip() for v in raw
    ):
        raise FactsError("forbidden must be a list of non-empty strings")
    return list(raw)


class KeyFactsEvaluator:
    def __init__(
        self,
        required: list | None = None,
        forbidden: list | str | None = None,
        threshold: float = 1.0,
        case_sensitive: bool = False,
        normalize_whitespace: bool = True,
        field: str | None = None,
    ):
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
            raise ValueError("threshold must be a number in (0, 1]")
        if not 0 < threshold <= 1:
            raise ValueError("threshold must be in (0, 1]")
        self.required = _parse_required(required)
        self.forbidden = _parse_forbidden(forbidden)
        self.threshold = float(threshold)
        self.case_sensitive = case_sensitive
        self.normalize_whitespace = normalize_whitespace
        self.field = field

    def _norm(self, s: str) -> str:
        if self.normalize_whitespace:
            s = " ".join(s.split())
        return s if self.case_sensitive else s.casefold()

    def run(self, response: str) -> Score:
        # No case context (contract mode): only config-level facts apply.
        return self.run_case(response, {}) or Score(
            value=0.0,
            reason="key_facts: no facts: set required/forbidden or use a "
            "dataset case with metadata.key_facts",
        )

    def run_case(self, response: str, case: dict) -> Score | None:
        """Score one case; ``None`` = not applicable (no facts anywhere)."""
        try:
            required, forbidden = self._facts_for(case)
        except FactsError as e:
            return Score(value=0.0, reason=f"{_NAME}: invalid facts: {e}")
        if not required and not forbidden:
            return None
        if self.field:
            response, err = extract_text_field(response, self.field, _NAME)
            if err is not None:
                return err
        answer, _ = split_reasoning(response)
        text = self._norm(answer)

        hits = [f for f in forbidden if self._norm(f) in text]
        missing = [
            v for v in required if not any(self._norm(x) in text for x in v)
        ]
        found = len(required) - len(missing)
        coverage = found / len(required) if required else 1.0
        meta = {"found": found, "total": len(required), "coverage": coverage}

        problems: list[str] = []
        if missing:
            shown = "; ".join(" | ".join(repr(x) for x in v) for v in missing)
            problems.append(f"missing {len(missing)}/{len(required)} facts: {shown}")
        if hits:
            problems.append("forbidden present: " + ", ".join(repr(h) for h in hits))
        if hits:
            return Score(value=0.0, reason="; ".join(problems), metadata=meta)
        if coverage >= self.threshold:
            reason = "; ".join(problems) or None
            if problems:
                reason += f" (coverage {found}/{len(required)} meets threshold {self.threshold:g})"
            return Score(value=1.0, reason=reason, metadata=meta)
        return Score(value=coverage, reason="; ".join(problems), metadata=meta)

    def _facts_for(self, case: dict) -> tuple[list[list[str]], list[str]]:
        meta = case.get("metadata") or {}
        block = meta.get("key_facts") if isinstance(meta, dict) else None
        if block is not None:
            if not isinstance(block, dict):
                raise FactsError("metadata.key_facts must be a mapping")
            required = _parse_required(block.get("required"))
            forbidden = _parse_forbidden(block.get("forbidden"))
            if required or forbidden:
                return required, forbidden
        return self.required, self.forbidden
