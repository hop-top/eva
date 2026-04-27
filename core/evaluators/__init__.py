# core/evaluators/__init__.py
from core.evaluators.contains import ContainsEvaluator
from core.evaluators.regex_match import RegexEvaluator
from core.evaluators.json_schema_valid import JsonSchemaEvaluator
from core.evaluators.no_pii import NoPiiEvaluator
from core.evaluators.status_code import StatusCodeEvaluator, ExitCodeEvaluator
from core.evaluators.equals import EqualsEvaluator
from core.evaluators.llm_judge import (
    RelevanceEvaluator,
    HallucinationEvaluator,
    ToneEvaluator,
    TaskCompletionEvaluator,
    SafetyEvaluator,
    parse_score,
)

# Name -> class registry. Used by contract loader to resolve `type:` /
# `name:` references in YAML. exit_code is an alias for status_code —
# both names resolve to the same class.
EVALUATOR_REGISTRY = {
    "contains": ContainsEvaluator,
    "regex": RegexEvaluator,
    "json_schema_valid": JsonSchemaEvaluator,
    "no_pii": NoPiiEvaluator,
    "status_code": StatusCodeEvaluator,
    "exit_code": ExitCodeEvaluator,  # alias for status_code
    "equals": EqualsEvaluator,
    "relevance": RelevanceEvaluator,
    "hallucination": HallucinationEvaluator,
    "tone": ToneEvaluator,
    "task_completion": TaskCompletionEvaluator,
    "safety": SafetyEvaluator,
}

__all__ = [
    "ContainsEvaluator",
    "RegexEvaluator",
    "JsonSchemaEvaluator",
    "NoPiiEvaluator",
    "StatusCodeEvaluator",
    "ExitCodeEvaluator",
    "EqualsEvaluator",
    "RelevanceEvaluator",
    "HallucinationEvaluator",
    "ToneEvaluator",
    "TaskCompletionEvaluator",
    "SafetyEvaluator",
    "EVALUATOR_REGISTRY",
    "parse_score",
]
