# core/evaluators/plan_adherence.py
"""PlanAdherenceEvaluator — rates execution fidelity vs planned step sequence.

US-032 Tier-2 LLM-judge evaluator. See `tool_correctness.py` for the
rationale behind re-exporting from `llm_judge.py`.
"""
from __future__ import annotations

from core.evaluators.llm_judge import PlanAdherenceEvaluator

__all__ = ["PlanAdherenceEvaluator"]
