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
The score is always the true coverage. ``threshold`` (default 1.0 = every
fact) is the coverage that passes: the default-pass-rule hook turns it into
``mode: threshold`` / ``min_score`` (see ``key_facts_pass_rule``).
Matching is case-insensitive and whitespace-normalised by default.

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


class KeyFactsConfigError(ValueError):
    """Contradictory pass settings (``threshold`` vs ``mode``/``min_score``).

    A ``ValueError`` so pydantic reports it as a validation error (contract
    load, ``/v1/proxy``); the pass-rule hook runs outside the factory ``try``
    in runners, so it is never mistaken for "evaluator unavailable".
    """


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
        return Score(
            value=coverage, reason="; ".join(problems) or None, metadata=meta
        )

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


def make_key_facts(cfg: dict, _llm: Any = None) -> KeyFactsEvaluator:
    return KeyFactsEvaluator(
        required=cfg.get("required"),
        forbidden=cfg.get("forbidden"),
        threshold=cfg.get("threshold", 1.0),
        case_sensitive=cfg.get("case_sensitive", False),
        normalize_whitespace=cfg.get("normalize_whitespace", True),
        field=cfg.get("field"),
    )


def key_facts_pass_rule(
    config: dict, mode: str | None, min_score: float | None
) -> tuple[str, float] | None:
    """Default pass rule from ``threshold``: ``(mode, min_score)`` or ``None``.

    ``mode`` / ``min_score`` are what the user set (``None`` = not set).
    Unset: ``mode: threshold`` with ``min_score = threshold`` (default 1.0).
    Explicit ``binary`` / ``warn`` are kept (``None``); an explicit
    ``min_score`` wins and implies ``threshold`` mode. A setting that
    contradicts an explicit ``threshold`` raises ``KeyFactsConfigError``.
    """
    threshold_set = "threshold" in config
    threshold = config.get("threshold", 1.0)
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        return None  # the evaluator factory reports the bad threshold
    if min_score is not None and threshold_set and abs(min_score - threshold) > 1e-9:
        raise KeyFactsConfigError(
            f"{_NAME}: threshold {threshold:g} conflicts with min_score "
            f"{min_score:g}; set one of them"
        )
    if mode == "binary" and threshold_set and threshold != 1.0:
        raise KeyFactsConfigError(
            f"{_NAME}: threshold {threshold:g} conflicts with mode: binary "
            "(needs every fact); use mode: threshold or drop mode"
        )
    if mode in ("binary", "warn"):
        return None
    return "threshold", float(threshold if min_score is None else min_score)
