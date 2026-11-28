# core/evaluators/config_values.py
"""Typed reads of evaluator config values.

The factories in ``builtin`` read user config (dataset entry, contract
evaluator, gateway ``config``) through these, so a wrong-typed value is an
``EvaluatorConfigError`` naming the key and the value rather than a
``TypeError`` raised from deep inside an evaluator, or silently accepted and
misbehaving at run time. ``build_evaluator`` adds the evaluator name.
"""
from __future__ import annotations

import re
from typing import Any, Sequence

from core.evaluators.errors import EvaluatorConfigError


def _bad(key: str, want: str, value: Any) -> EvaluatorConfigError:
    return EvaluatorConfigError(f"{key} must be {want}; got {value!r}")


def string(cfg: dict, key: str, default: str = "") -> str:
    value = cfg.get(key, default)
    if not isinstance(value, str):
        raise _bad(key, "a string", value)
    return value


def opt_string(cfg: dict, key: str) -> str | None:
    value = cfg.get(key)
    if value is not None and not isinstance(value, str):
        raise _bad(key, "a string", value)
    return value


def boolean(cfg: dict, key: str, default: bool) -> bool:
    value = cfg.get(key, default)
    if not isinstance(value, bool):
        raise _bad(key, "true or false", value)
    return value


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def integer(cfg: dict, key: str, default: int) -> int:
    value = cfg.get(key, default)
    if not _is_int(value):
        raise _bad(key, "an integer", value)
    return value


def opt_integer(cfg: dict, key: str) -> int | None:
    value = cfg.get(key)
    if value is not None and not _is_int(value):
        raise _bad(key, "an integer", value)
    return value


def seconds(cfg: dict, key: str, default: float) -> float:
    value = cfg.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise _bad(key, "a positive number of seconds", value)
    return value


def choice(cfg: dict, key: str, default: str, options: Sequence[str]) -> str:
    value = cfg.get(key, default)
    if not isinstance(value, str) or value not in options:
        raise _bad(key, "one of " + ", ".join(repr(o) for o in options), value)
    return value


def mapping(cfg: dict, key: str, default: dict | None = None) -> dict:
    value = cfg.get(key, {} if default is None else default)
    if not isinstance(value, dict):
        raise _bad(key, "an object (mapping)", value)
    return value


def _list_of(cfg: dict, key: str, ok: Any, what: str, default: Any) -> Any:
    value = cfg.get(key, default)
    if value is None or not isinstance(value, (list, tuple)) or not all(ok(v) for v in value):
        raise _bad(key, what, value)
    return list(value)


def strings(cfg: dict, key: str, default: Sequence[str] = ()) -> list[str]:
    return _list_of(cfg, key, lambda v: isinstance(v, str), "a list of strings", list(default))


def opt_strings(cfg: dict, key: str) -> list[str] | None:
    return None if cfg.get(key) is None else strings(cfg, key)


def opt_integers(cfg: dict, key: str) -> list[int] | None:
    if cfg.get(key) is None:
        return None
    return _list_of(cfg, key, _is_int, "a list of integers", [])


def opt_mappings(cfg: dict, key: str) -> list[dict | None] | None:
    if cfg.get(key) is None:
        return None
    return _list_of(
        cfg, key, lambda v: v is None or isinstance(v, dict), "a list of objects", []
    )


def pattern(cfg: dict, key: str, default: str = ".*", flags: int = 0) -> str:
    """A regular expression string that compiles."""
    value = string(cfg, key, default)
    try:
        re.compile(value, flags)
    except re.error as e:
        raise EvaluatorConfigError(
            f"{key}: invalid regular expression {value!r}: {e.msg}"
        ) from e
    return value
