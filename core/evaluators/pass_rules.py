# core/evaluators/pass_rules.py
"""Default pass rules: an evaluator's config may imply its ``mode``/``min_score``.

A rule is ``(config, mode, min_score) -> (mode, min_score) | None`` where
``mode`` / ``min_score`` are the values the USER set (``None`` = unset) and
``None`` means "leave the defaults". Consulted wherever an evaluator spec is
built from user config (``EvaluatorRef``, gateway ``EvaluatorSpec``, dataset
evaluator entries), and only through ``resolve_pass_rule``, so every path
agrees. Evaluators without a rule are untouched.
"""
from __future__ import annotations

from typing import Callable

from core.evaluators.key_facts import key_facts_pass_rule

PassRule = Callable[[dict, "str | None", "float | None"], "tuple[str, float] | None"]

DEFAULT_PASS_RULES: dict[str, PassRule] = {
    "key_facts": key_facts_pass_rule,
}


def resolve_pass_rule(
    name: str, config: dict, mode: str | None, min_score: float | None
) -> tuple[str, float] | None:
    rule = DEFAULT_PASS_RULES.get(name)
    return rule(config, mode, min_score) if rule else None


def with_default_pass_rule(cfg: dict) -> dict:
    """Flat evaluator dict (dataset form: config keys beside ``mode``).

    Returns ``cfg`` itself when no rule applies, else a copy with ``mode`` and
    ``min_score`` filled in.
    """
    resolved = resolve_pass_rule(
        cfg.get("name", ""), cfg, cfg.get("mode"), cfg.get("min_score")
    )
    if resolved is None:
        return cfg
    return {**cfg, "mode": resolved[0], "min_score": resolved[1]}
