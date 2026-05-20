# core/evaluators/tool_correctness.py
"""ToolCorrectnessEvaluator — verifies the agent called the expected tools.

US-032 Tier-2 LLM-judge evaluator.

The canonical implementation lives in `core/evaluators/llm_judge.py` together
with sibling tool-use evaluators because they share the same judge-prompt
contract, parse_score() helper, and `evaluate(prompt, response, **context)`
signature. This module re-exports the class so registry consumers can refer
to it under its US-032 module name (`core.evaluators.tool_correctness`).
"""
from __future__ import annotations

from core.evaluators.llm_judge import ToolCorrectnessEvaluator

__all__ = ["ToolCorrectnessEvaluator"]
