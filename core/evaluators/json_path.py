# core/evaluators/json_path.py
"""Tier-2 deterministic JSON-path evaluator (T-0318, US-045).

Parse a JSON response, resolve a dotted/bracketed path, and compare the
value at that path against an expected value with one of five comparators.

v1 ships a stdlib pointer-walk fallback — no `jsonpath-ng` dep. Supports:
- dotted keys: `a.b.c`
- bracket-indexed arrays: `items[0].name`

Deferred to v2 if `jsonpath-ng` is added: wildcards, recursive descent,
filter expressions.
"""
from __future__ import annotations

import json
import re
from typing import Any, Literal

from core.models import Score


Comparator = Literal["eq", "neq", "gt", "lt", "in"]

_SEGMENT = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


class JsonPathEvaluator:
    def __init__(
        self,
        path: str,
        comparator: Comparator = "eq",
        expected: Any = None,
    ):
        if comparator not in {"eq", "neq", "gt", "lt", "in"}:
            raise ValueError(f"unsupported comparator: {comparator}")
        self.path = path
        self.comparator = comparator
        self.expected = expected

    def run(self, response: str) -> Score:
        try:
            doc = json.loads(response)
        except json.JSONDecodeError as e:
            return Score(value=0.0, reason=f"invalid json: {e}")

        try:
            value = _walk(doc, self.path)
        except KeyError:
            return Score(
                value=0.0,
                reason=f"path '{self.path}' not found",
            )

        ok, reason = _compare(value, self.comparator, self.expected)
        if ok:
            return Score(value=1.0)
        return Score(value=0.0, reason=reason)

    _run = run  # deprecated alias; remove in v0.2.0


def _walk(doc: Any, path: str) -> Any:
    """Walk a dotted/bracketed path. Raises KeyError on missing nodes."""
    cur: Any = doc
    # Split on dots, then within each token handle bracket-index suffixes.
    for token in path.split("."):
        if not token:
            continue
        # Pull off the key portion (everything up to the first '[').
        if "[" in token:
            key, rest = token.split("[", 1)
            indices = re.findall(r"(\d+)\]", "[" + rest)
        else:
            key, indices = token, []

        if key:
            if not isinstance(cur, dict) or key not in cur:
                raise KeyError(key)
            cur = cur[key]

        for idx_str in indices:
            idx = int(idx_str)
            if not isinstance(cur, list) or idx >= len(cur) or idx < -len(cur):
                raise KeyError(idx_str)
            cur = cur[idx]

    return cur


def _compare(value: Any, comparator: Comparator, expected: Any) -> tuple[bool, str]:
    if comparator == "eq":
        if value == expected:
            return True, ""
        return False, f"value {value!r} != expected {expected!r}"
    if comparator == "neq":
        if value != expected:
            return True, ""
        return False, f"value {value!r} == expected {expected!r} (neq)"
    if comparator == "gt":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False, f"value at path is not numeric: {type(value).__name__}"
        if value > expected:
            return True, ""
        return False, f"value {value!r} not > {expected!r}"
    if comparator == "lt":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False, f"value at path is not numeric: {type(value).__name__}"
        if value < expected:
            return True, ""
        return False, f"value {value!r} not < {expected!r}"
    if comparator == "in":
        if not isinstance(expected, (list, tuple, set)):
            return False, f"'in' expected must be a list (got {type(expected).__name__})"
        if value in expected:
            return True, ""
        return False, f"value {value!r} not in {list(expected)!r}"
    return False, f"unsupported comparator: {comparator}"
