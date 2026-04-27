# core/evaluators/equals.py
"""Generic field-equality evaluator for flow exec steps.

Asserts a named field in a JSON step-output payload equals an expected
literal. Supports any JSON-representable value: string, int, float, bool,
list, dict.
"""
from __future__ import annotations

import json
from typing import Any

from core.models import Score


_MISSING = object()


class EqualsEvaluator:
    """Asserts ``payload[field] == expected``.

    Parameters
    ----------
    field:
        Name of the field to compare. Required.
    expected:
        The literal value the field must equal. Any JSON-representable
        type. ``None`` is a valid expected value — to express "not
        provided" use a different evaluator.
    step:
        Identifier of the flow step whose output to evaluate. Stored
        as metadata for the runner; not used inside ``_run``.
    """

    def __init__(
        self,
        field: str | None = None,
        expected: Any = _MISSING,
        step: str | None = None,
    ):
        if not field:
            raise ValueError("equals: 'field' is required")
        if expected is _MISSING:
            raise ValueError("equals: 'expected' is required")
        self.field = field
        self.expected = expected
        self.step = step

    def _run(self, response: str) -> Score:
        try:
            payload = json.loads(response)
        except json.JSONDecodeError as e:
            return Score(value=0.0, reason=f"equals: invalid JSON payload: {e}")
        if not isinstance(payload, dict):
            return Score(value=0.0, reason="equals: payload is not a JSON object")
        if self.field not in payload:
            return Score(value=0.0, reason=f"equals: field '{self.field}' missing from payload")

        actual = payload[self.field]
        if type(actual) is not type(self.expected) and not (
            # int/float cross-comparison is fine; everything else strict
            isinstance(actual, (int, float))
            and isinstance(self.expected, (int, float))
            and not isinstance(actual, bool)
            and not isinstance(self.expected, bool)
        ):
            return Score(
                value=0.0,
                reason=(
                    f"equals: type mismatch on '{self.field}': "
                    f"expected {type(self.expected).__name__}, got {type(actual).__name__}"
                ),
            )

        if actual == self.expected:
            return Score(value=1.0)
        return Score(
            value=0.0,
            reason=f"equals: '{self.field}' expected {self.expected!r}, got {actual!r}",
        )
