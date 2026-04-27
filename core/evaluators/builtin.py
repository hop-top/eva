# core/evaluators/builtin.py
"""Built-in evaluator factory registry.

Single source of truth used by both the gateway (server/gateway/routes.py)
and the standalone CLI (cli/run_contract.py). Each factory takes a config
dict and returns an evaluator instance with a `_run(response: str) -> Score`
method.

Adding a new built-in evaluator: register it here. Both call sites pick it
up automatically.
"""
from __future__ import annotations

from typing import Any, Callable

from core.evaluators.contains import ContainsEvaluator
from core.evaluators.json_schema_valid import JsonSchemaEvaluator
from core.evaluators.no_pii import NoPiiEvaluator
from core.evaluators.regex_match import RegexEvaluator


EvaluatorFactory = Callable[[dict], Any]


BUILTIN_EVALUATOR_FACTORIES: dict[str, EvaluatorFactory] = {
    "contains": lambda cfg: ContainsEvaluator(
        substring=cfg.get("substring", ""),
        case_sensitive=cfg.get("case_sensitive", True),
    ),
    "regex": lambda cfg: RegexEvaluator(pattern=cfg.get("pattern", ".*")),
    "json_schema_valid": lambda cfg: JsonSchemaEvaluator(schema=cfg.get("schema", {})),
    "no_pii": lambda cfg: NoPiiEvaluator(),
}
