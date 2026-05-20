# core/evaluators/rag.py
"""RAG evaluators (US-031).

Six LLM-judge evaluators scoped to RAG pipelines:

* :class:`RAGFaithfulnessEvaluator` — claims grounded in ``retrieval_context``.
* :class:`RAGContextualRelevancyEvaluator` — relevance of retrieved chunks to the query.
* :class:`RAGContextualPrecisionEvaluator` — signal-to-noise of retrieved chunks.
* :class:`RAGContextualRecallEvaluator` — coverage of expected content by retrieved chunks.
* :class:`RAGAnswerRelevancyEvaluator` — direct answer quality (query-only, no context required).
* :class:`RAGASEvaluator` — composite that averages the three contextual evaluators plus
  answer relevancy and returns a per-component breakdown in ``metadata``.

Class names are RAG-prefixed to avoid collision with same-named legacy classes in
``core/evaluators/llm_judge.py``. Registry keys use the ``rag:`` namespace (e.g.
``rag:faithfulness``).

All evaluators consume the eva evaluator context via ``**context`` and read
``retrieval_context`` and ``expected_output`` from it. Any evaluator that depends on
``retrieval_context`` degrades gracefully when the field is missing by returning a
fallback :class:`~core.models.Score` of 0.5 with an explanatory ``reason`` rather than
calling the LLM with an empty context.
"""
from __future__ import annotations

from typing import Any

from core.evaluators.llm_judge import parse_score
from core.models import Score


_MISSING_CTX_FALLBACK = 0.5


def _fallback_no_context(evaluator_id: str) -> Score:
    """Score returned when an evaluator requires retrieval_context and none was given."""
    return Score(
        value=_MISSING_CTX_FALLBACK,
        reason="retrieval_context not provided; returning fallback score",
        metadata={"evaluator_id": evaluator_id, "fallback": True},
    )


class RAGFaithfulnessEvaluator:
    """Rate how faithfully the response is grounded in retrieval_context.

    If ``retrieval_context`` is absent, the evaluator degrades gracefully to a
    general grounding check against the prompt rather than failing.
    """

    evaluator_id = "faithfulness"

    def __init__(self, llm_adapter: Any):
        self.llm = llm_adapter

    async def evaluate(self, prompt: str, response: str, **context: Any) -> Score:
        retrieval_context = context.get("retrieval_context") or ""
        if retrieval_context:
            judge_prompt = (
                "You are evaluating RAG faithfulness. Score 0.0-1.0 where 1.0 means every "
                "claim in the response is grounded in the retrieval context and 0.0 means "
                "the response contradicts or hallucinates beyond the context.\n"
                f"Retrieval context:\n{retrieval_context}\n"
                f"Response:\n{response}\n"
                "Reply with the float on the first line, then a brief justification."
            )
        else:
            judge_prompt = (
                "No retrieval context was supplied. Rate the response's general factual "
                "grounding on a 0.0-1.0 scale (1.0 = well-supported claims, 0.0 = "
                "hallucinated).\n"
                f"Prompt: {prompt}\n"
                f"Response: {response}\n"
                "Reply with the float on the first line, then a brief justification."
            )
        completion = await self.llm.complete([{"role": "user", "content": judge_prompt}])
        value, reason = parse_score(completion.content)
        return Score(
            value=value,
            reason=reason,
            metadata={
                "evaluator_id": self.evaluator_id,
                "had_retrieval_context": bool(retrieval_context),
            },
        )


class RAGContextualRelevancyEvaluator:
    """Rate how relevant the retrieved context is to the user query."""

    evaluator_id = "contextual_relevancy"

    def __init__(self, llm_adapter: Any):
        self.llm = llm_adapter

    async def evaluate(self, prompt: str, response: str, **context: Any) -> Score:
        retrieval_context = context.get("retrieval_context") or ""
        if not retrieval_context:
            return _fallback_no_context(self.evaluator_id)
        judge_prompt = (
            "Rate, on a 0.0-1.0 scale, how relevant the retrieved context is to the user's "
            "query. 1.0 = directly answers the query, 0.0 = unrelated.\n"
            f"Query: {prompt}\n"
            f"Retrieval context:\n{retrieval_context}\n"
            "Reply with the float on the first line, then a brief justification."
        )
        completion = await self.llm.complete([{"role": "user", "content": judge_prompt}])
        value, reason = parse_score(completion.content)
        return Score(value=value, reason=reason, metadata={"evaluator_id": self.evaluator_id})


class RAGContextualPrecisionEvaluator:
    """Rate the signal-to-noise ratio of the retrieved context."""

    evaluator_id = "contextual_precision"

    def __init__(self, llm_adapter: Any):
        self.llm = llm_adapter

    async def evaluate(self, prompt: str, response: str, **context: Any) -> Score:
        retrieval_context = context.get("retrieval_context") or ""
        if not retrieval_context:
            return _fallback_no_context(self.evaluator_id)
        judge_prompt = (
            "Rate the signal-to-noise ratio of the retrieved context on a 0.0-1.0 scale. "
            "1.0 = every chunk is on-topic and useful for answering the query; 0.0 = "
            "mostly irrelevant or distracting chunks dominate the context.\n"
            f"Query: {prompt}\n"
            f"Retrieval context:\n{retrieval_context}\n"
            "Reply with the float on the first line, then a brief justification."
        )
        completion = await self.llm.complete([{"role": "user", "content": judge_prompt}])
        value, reason = parse_score(completion.content)
        return Score(value=value, reason=reason, metadata={"evaluator_id": self.evaluator_id})


class RAGContextualRecallEvaluator:
    """Rate how completely the retrieved context covers the expected answer.

    Requires either ``expected_output`` passed in context or via constructor.
    """

    evaluator_id = "contextual_recall"

    def __init__(self, llm_adapter: Any, expected_output: str | None = None):
        self.llm = llm_adapter
        self.expected_output = expected_output

    async def evaluate(self, prompt: str, response: str, **context: Any) -> Score:
        retrieval_context = context.get("retrieval_context") or ""
        if not retrieval_context:
            return _fallback_no_context(self.evaluator_id)
        expected = self.expected_output or context.get("expected_output") or ""
        judge_prompt = (
            "Rate how completely the retrieval context covers the information needed to "
            "produce the expected output on a 0.0-1.0 scale. 1.0 = every fact required for "
            "the expected output is present in the context; 0.0 = key facts are missing.\n"
            f"Expected output: {expected}\n"
            f"Retrieval context:\n{retrieval_context}\n"
            "Reply with the float on the first line, then a brief justification."
        )
        completion = await self.llm.complete([{"role": "user", "content": judge_prompt}])
        value, reason = parse_score(completion.content)
        return Score(value=value, reason=reason, metadata={"evaluator_id": self.evaluator_id})


class RAGAnswerRelevancyEvaluator:
    """Rate how directly and completely the response answers the query.

    Does not require retrieval_context — the query/response pair is sufficient.
    """

    evaluator_id = "answer_relevancy"

    def __init__(self, llm_adapter: Any):
        self.llm = llm_adapter

    async def evaluate(self, prompt: str, response: str, **context: Any) -> Score:
        judge_prompt = (
            "Rate how directly and completely the response answers the query on a 0.0-1.0 "
            "scale. 1.0 = fully and concisely answers the query; 0.0 = off-topic.\n"
            f"Query: {prompt}\n"
            f"Response: {response}\n"
            "Reply with the float on the first line, then a brief justification."
        )
        completion = await self.llm.complete([{"role": "user", "content": judge_prompt}])
        value, reason = parse_score(completion.content)
        return Score(value=value, reason=reason, metadata={"evaluator_id": self.evaluator_id})


class RAGASEvaluator:
    """Composite RAG score (RAGAS-style).

    Averages the three contextual evaluators plus answer relevancy and exposes a
    per-component breakdown via ``score.metadata['component_scores']``. Custom
    component sets can be injected via ``evaluators=[...]``; otherwise pass an
    ``llm_adapter`` and the default four-component set is built.

    The composite degrades gracefully: when ``retrieval_context`` is missing, the
    sub-evaluators themselves fall back, so the composite still returns a Score.
    """

    evaluator_id = "ragas"

    def __init__(
        self,
        evaluators: list | None = None,
        llm_adapter: Any | None = None,
    ):
        if evaluators is not None:
            self.evaluators = evaluators
        elif llm_adapter is not None:
            self.evaluators = [
                RAGFaithfulnessEvaluator(llm_adapter),
                RAGContextualRelevancyEvaluator(llm_adapter),
                RAGContextualPrecisionEvaluator(llm_adapter),
                RAGContextualRecallEvaluator(llm_adapter),
                RAGAnswerRelevancyEvaluator(llm_adapter),
            ]
        else:
            self.evaluators = []

    async def evaluate(self, prompt: str, response: str, **context: Any) -> Score:
        scores: list[Score] = []
        for ev in self.evaluators:
            s = await ev.evaluate(prompt, response, **context)
            scores.append(s)

        if not scores:
            return Score(
                value=0.0,
                reason="No component evaluators configured",
                metadata={"evaluator_id": self.evaluator_id, "component_scores": {}},
            )

        avg = sum(s.value for s in scores) / len(scores)
        component_scores: dict[str, float] = {}
        for i, s in enumerate(scores):
            key = s.metadata.get("evaluator_id", f"component_{i}")
            component_scores[key] = s.value
        reasons = [s.reason for s in scores if s.reason]
        return Score(
            value=avg,
            reason="; ".join(reasons) if reasons else None,
            metadata={
                "evaluator_id": self.evaluator_id,
                "component_scores": component_scores,
            },
        )


__all__ = [
    "RAGFaithfulnessEvaluator",
    "RAGContextualRelevancyEvaluator",
    "RAGContextualPrecisionEvaluator",
    "RAGContextualRecallEvaluator",
    "RAGAnswerRelevancyEvaluator",
    "RAGASEvaluator",
]
