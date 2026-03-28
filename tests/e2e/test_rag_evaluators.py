# tests/e2e/test_rag_evaluators.py
"""E2E tests: RAG evaluators wired to dataset loading."""
import io
import pytest
import yaml
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from core.dataset import EvaTestCase, load_dataset
from core.evaluators.llm_judge import (
    AnswerRelevancyEvaluator,
    ContextualPrecisionEvaluator,
    ContextualRecallEvaluator,
    ContextualRelevancyEvaluator,
    FaithfulnessEvaluator,
    RAGASEvaluator,
)
from core.models import Score


def make_mock_llm(reply: str) -> AsyncMock:
    mock = AsyncMock()
    completion = MagicMock()
    completion.content = reply
    mock.complete = AsyncMock(return_value=completion)
    return mock


# ---------------------------------------------------------------------------
# FaithfulnessEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_faithfulness_with_retrieval_context():
    tc = EvaTestCase(
        id="tc-001",
        input="What is Python?",
        retrieval_context="Python is a high-level programming language.",
    )
    llm = make_mock_llm("0.85\nAll claims grounded in context.")
    ev = FaithfulnessEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt=tc.input,
        response="Python is a high-level language.",
        retrieval_context=tc.retrieval_context,
    )
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.85)


@pytest.mark.asyncio
async def test_faithfulness_without_retrieval_context():
    tc = EvaTestCase(id="tc-002", input="What is Go?")
    llm = make_mock_llm("0.7\nGeneral grounding looks reasonable.")
    ev = FaithfulnessEvaluator(llm_adapter=llm)
    score = await ev.evaluate(prompt=tc.input, response="Go is a compiled language.")
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# Contextual evaluators
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_contextual_relevancy():
    tc = EvaTestCase(
        id="tc-003",
        input="Explain RAG",
        retrieval_context="RAG stands for Retrieval-Augmented Generation.",
    )
    llm = make_mock_llm("0.9\nContext is highly relevant to the query.")
    ev = ContextualRelevancyEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt=tc.input,
        response="RAG combines retrieval with generation.",
        retrieval_context=tc.retrieval_context,
    )
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_contextual_precision():
    tc = EvaTestCase(
        id="tc-004",
        input="What is embeddings?",
        retrieval_context="Embeddings are vector representations of text.",
    )
    llm = make_mock_llm("0.8\nAll retrieved content is relevant.")
    ev = ContextualPrecisionEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt=tc.input,
        response="Embeddings map text to vectors.",
        retrieval_context=tc.retrieval_context,
    )
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_contextual_recall():
    tc = EvaTestCase(
        id="tc-005",
        input="What is LLM?",
        expected_output="LLM stands for Large Language Model.",
        retrieval_context="LLMs are large neural networks trained on text.",
    )
    llm = make_mock_llm("0.75\nContext covers most of expected output.")
    ev = ContextualRecallEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt=tc.input,
        response="LLMs are neural networks.",
        retrieval_context=tc.retrieval_context,
        expected_output=tc.expected_output,
    )
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# AnswerRelevancyEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_answer_relevancy():
    tc = EvaTestCase(id="tc-006", input="What is FAISS?")
    llm = make_mock_llm("0.95\nResponse directly answers the question.")
    ev = AnswerRelevancyEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt=tc.input,
        response="FAISS is a library for efficient similarity search.",
    )
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.95)


# ---------------------------------------------------------------------------
# RAGASEvaluator — composite
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ragas_composite_averages_components():
    def make_sub(val: float):
        class _Sub:
            evaluator_id = f"sub_{val}"
            async def evaluate(self, prompt, response, **_kw):
                return Score(
                    value=val,
                    reason="mock",
                    metadata={"evaluator_id": self.evaluator_id},
                )
        return _Sub()

    sub1 = make_sub(0.8)
    sub2 = make_sub(0.6)
    sub3 = make_sub(1.0)

    ev = RAGASEvaluator(evaluators=[sub1, sub2, sub3])
    score = await ev.evaluate(prompt="q", response="a")

    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.8)
    assert "component_scores" in score.metadata
    assert len(score.metadata["component_scores"]) == 3


# ---------------------------------------------------------------------------
# Dataset loading — retrieval_context field
# ---------------------------------------------------------------------------

def test_dataset_loads_retrieval_context(tmp_path: Path):
    yaml_content = """
name: rag-test
target: http://localhost:9999
tests:
  - id: tc-r01
    input: What is vector search?
    retrieval_context: "Vector search finds similar items using embeddings."
"""
    ds_file = tmp_path / "rag_dataset.yaml"
    ds_file.write_text(yaml_content)

    dataset = load_dataset(ds_file)
    assert len(dataset.tests) == 1
    tc = dataset.tests[0]
    assert tc.retrieval_context == "Vector search finds similar items using embeddings."
