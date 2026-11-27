# core/evaluators/_field.py
"""Shared ``field`` lookup for evaluators that scope to a JSON payload field.

Single implementation of the rules ``equals`` uses: the input must parse as a
JSON object and ``field`` must be a top-level key. No nested/dotted paths.
"""
from __future__ import annotations

import json
from typing import Any

from core.models import Score


def extract_field(response: str, field: str, name: str) -> tuple[Any, Score | None]:
    """Return ``(value, None)`` on success or ``(None, failing Score)``.

    ``name`` prefixes the failure reason (e.g. ``"equals"``, ``"regex"``).
    """
    try:
        payload = json.loads(response)
    except json.JSONDecodeError as e:
        return None, Score(value=0.0, reason=f"{name}: invalid JSON payload: {e}")
    if not isinstance(payload, dict):
        return None, Score(value=0.0, reason=f"{name}: payload is not a JSON object")
    if field not in payload:
        return None, Score(value=0.0, reason=f"{name}: field '{field}' missing from payload")
    return payload[field], None


def extract_text_field(response: str, field: str, name: str) -> tuple[str | None, Score | None]:
    """Like ``extract_field`` but the value must be a string (no coercion)."""
    value, err = extract_field(response, field, name)
    if err is not None:
        return None, err
    if not isinstance(value, str):
        return None, Score(
            value=0.0,
            reason=f"{name}: field '{field}' is not a string (got {type(value).__name__})",
        )
    return value, None
