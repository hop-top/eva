# core/evaluators/plan_quality.py
"""PlanQualityEvaluator — rates plan quality independent of execution.

US-032 Tier-2 LLM-judge evaluator. See `tool_correctness.py` for the
rationale behind re-exporting from `llm_judge.py`.
"""
from __future__ import annotations

from core.evaluators.llm_judge import PlanQualityEvaluator

__all__ = ["PlanQualityEvaluator"]
