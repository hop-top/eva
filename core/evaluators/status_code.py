# core/evaluators/status_code.py
"""Status/exit code evaluator for flow exec steps.

Asserts that a step's ``exit_code`` (or HTTP-style ``status_code``) field
matches an expected integer or falls within an allowed set.

The evaluator receives the step output as a JSON-encoded string. The
``step`` attribute is metadata used by the flow runner to route the
correct step's output here; ``run`` itself only inspects the payload.
"""
from __future__ import annotations

import json
from typing import Iterable

from core.models import Score


# Field aliases checked in order — first match wins.
_FIELDS = ("exit_code", "status_code")


class StatusCodeEvaluator:
    """Asserts step exit_code/status_code matches expected value(s).

    Parameters
    ----------
    step:
        Identifier of the flow step whose output should be evaluated.
        Stored as metadata for the runner; not used inside ``run``.
    expected:
        Single integer that must match exactly. Mutually exclusive with
        ``expected_in``.
    expected_in:
        Iterable of integers. Score is 1.0 if the actual value is in
        this set. Mutually exclusive with ``expected``.
    """

    def __init__(
        self,
        step: str | None = None,
        expected: int | None = None,
        expected_in: Iterable[int] | None = None,
    ):
        if expected is None and expected_in is None:
            raise ValueError("status_code: must provide 'expected' or 'expected_in'")
        if expected is not None and expected_in is not None:
            raise ValueError("status_code: 'expected' and 'expected_in' are mutually exclusive")
        self.step = step
        self.expected = expected
        self.expected_in = list(expected_in) if expected_in is not None else None

    def _extract(self, payload: dict) -> int | None:
        for field in _FIELDS:
            if field in payload:
                value = payload[field]
                if isinstance(value, bool) or not isinstance(value, int):
                    return None
                return value
        return None

    def run(self, response: str) -> Score:
        try:
            payload = json.loads(response)
        except json.JSONDecodeError as e:
            return Score(value=0.0, reason=f"status_code: invalid JSON payload: {e}")
        if not isinstance(payload, dict):
            return Score(value=0.0, reason="status_code: payload is not a JSON object")

        actual = self._extract(payload)
        if actual is None:
            return Score(
                value=0.0,
                reason=f"status_code: no integer '{_FIELDS[0]}' or '{_FIELDS[1]}' field in payload",
            )

        if self.expected_in is not None:
            if actual in self.expected_in:
                return Score(value=1.0)
            return Score(
                value=0.0,
                reason=f"status_code: {actual} not in expected_in {self.expected_in}",
            )

        if actual == self.expected:
            return Score(value=1.0)
        return Score(
            value=0.0,
            reason=f"status_code: expected {self.expected}, got {actual}",
        )

    _run = run  # deprecated alias; remove in v0.2.0


# Alias — exit_code is the field name in tlc exec step output;
# status_code mirrors HTTP convention. Both names point at the same class.
ExitCodeEvaluator = StatusCodeEvaluator
