# core/evaluators/judge_support.py
"""Shared helpers for running LLM-judge evaluators outside dataset mode.

Contract mode (`eva run --contract`) and the gateway both score a single
(prompt, response) pair with judge evaluators. They share: which judge
evaluators can run from that pair alone, why the others are skipped, and how a
failed judge call becomes a `Score` instead of an exception.
"""
from __future__ import annotations

from typing import Any

from core.models import Score

# Judge evaluators (factories that need an llm_adapter) split by what they read
# beyond (prompt, response). A caller that supplies nothing else skips those in
# JUDGE_NEEDS with a precise reason instead of guessing inputs.
JUDGE_PROMPT_ONLY = frozenset({
    "relevance", "hallucination", "tone", "task_completion", "safety",
    "plan_quality", "geval", "rag:answer_relevancy", "rag:faithfulness",
    "content:bias", "content:toxicity", "content:summarization",
    "content:prompt_alignment",
})
# name -> (needed input, config key that supplies it, if any)
JUDGE_NEEDS: dict[str, tuple[str, str | None]] = {
    "tool_correctness": ("tool events", None),
    "argument_correctness": ("tool events", None),
    "tool_use": ("tool events", None),
    "step_efficiency": ("tool events", None),
    "plan_adherence": ("planned steps", None),
    "rag:contextual_relevancy": ("retrieval context", None),
    "rag:contextual_precision": ("retrieval context", None),
    "rag:contextual_recall": ("retrieval context", None),
    "ragas": ("retrieval context", None),
    "content:goal_accuracy": ("expected output", "expected_output"),
}

NO_JUDGE_REASON = "no judge model configured"


def missing_input_reason(name: str, cfg: dict, runner: str) -> str | None:
    """Reason `name` cannot run from (prompt, response) alone, else None.

    ``runner`` names who is running it ("a contract run", "the gateway").
    """
    need = JUDGE_NEEDS.get(name)
    if need is None or (need[1] and cfg.get(need[1])):
        return None
    return (
        f"needs {need[0]}, which {runner} cannot supply (use dataset mode)"
        if not need[1]
        else f"needs {need[0]}: set `{need[1]}` in the contract, or use dataset mode"
    )


def judge_skip_reason(
    name: str,
    cfg: dict,
    factory_error: ValueError,
    llm_adapter: Any | None,
    runner: str,
) -> str | None:
    """Why a judge evaluator cannot run, before any prompt check; None if it can.

    ``factory_error`` is the ValueError its factory raised when built without an
    adapter (which is how a judge evaluator is told apart from the others).
    """
    if llm_adapter is None:
        return NO_JUDGE_REASON
    if name not in JUDGE_PROMPT_ONLY and name not in JUDGE_NEEDS:
        # Unclassified: never guess inputs for it.
        return str(factory_error)
    return missing_input_reason(name, cfg, runner)


def build_judge(factory: Any, cfg: dict, llm_adapter: Any) -> tuple[Any | None, str | None]:
    """Build the judge evaluator: ``(evaluator, None)`` or ``(None, reason)``."""
    try:
        return factory(cfg, llm_adapter), None
    except (KeyError, TypeError) as e:
        return None, f"invalid evaluator config ({e})"


async def run_judge(evaluator: Any, prompt: str, response: str) -> Score:
    """Score ``(prompt, response)``; a failed judge call yields a 0.0 Score."""
    try:
        return await evaluator.evaluate(prompt=prompt, response=response)
    except Exception as e:  # endpoint down, timeout, auth, ...
        msg = (str(e).strip().splitlines() or [""])[0]
        return Score(
            value=0.0,
            reason=f"judge error: {type(e).__name__}: {msg}".rstrip(": "),
        )
