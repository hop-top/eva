# tests/e2e/test_rag_evaluators.py
"""E2E tests: RAG evaluators (US-031).

One ``test_us031_ac*`` case per acceptance bullet in
``docs/stories/US-031-rag-evaluation.md``:

  AC1: dataset YAML accepts ``retrieval_context``.
  AC2: ``faithfulness`` checks response claims against retrieval context.
  AC3: ``contextual_relevancy`` evaluates relevance of retrieved context to query.
  AC4: ``contextual_precision`` evaluates signal-to-noise of retrieved context.
  AC5: ``contextual_recall`` evaluates coverage of relevant context.
  AC6: ``answer_relevancy`` rates how well the response answers the query.
  AC7: ``ragas`` composite averages components + exposes per-component breakdown.
  AC8: all RAG evaluators degrade gracefully when ``retrieval_context`` is absent.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.dataset import EvaTestCase, load_dataset
from core.evaluators.rag import (
    RAGAnswerRelevancyEvaluator,
    RAGASEvaluator,
    RAGContextualPrecisionEvaluator,
    RAGContextualRecallEvaluator,
    RAGContextualRelevancyEvaluator,
    RAGFaithfulnessEvaluator,
)
from core.models import Score


def make_mock_llm(reply: str) -> AsyncMock:
    """Mock LLM adapter returning a single canned completion (reused pattern)."""
    mock = AsyncMock()
    completion = MagicMock()
    completion.content = reply
    mock.complete = AsyncMock(return_value=completion)
    return mock


def make_capturing_llm(reply: str) -> tuple[MagicMock, list]:
    """Mock that captures every ``complete()`` message-list it received."""
    captured: list = []

    async def capturing_complete(messages):
        captured.append(messages)
        completion = MagicMock()
        completion.content = reply
        return completion

    mock = MagicMock()
    mock.complete = capturing_complete
    return mock, captured


# ---------------------------------------------------------------------------
# AC1 — dataset YAML accepts retrieval_context
# ---------------------------------------------------------------------------

def test_us031_ac1_dataset_loads_retrieval_context(tmp_path: Path):
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


# Existing alias kept so other suites can still import the old name.
test_dataset_loads_retrieval_context = test_us031_ac1_dataset_loads_retrieval_context


# ---------------------------------------------------------------------------
# AC2 — faithfulness checks claims against retrieval_context
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_us031_ac2_faithfulness_with_retrieval_context():
    tc = EvaTestCase(
        id="tc-001",
        input="What is Python?",
        retrieval_context="Python is a high-level programming language.",
    )
    llm, captured = make_capturing_llm("0.85\nAll claims grounded in context.")
    ev = RAGFaithfulnessEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt=tc.input,
        response="Python is a high-level language.",
        retrieval_context=tc.retrieval_context,
    )
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.85)
    assert score.metadata["evaluator_id"] == "faithfulness"
    assert score.metadata["had_retrieval_context"] is True
    # The judge must have actually seen the retrieval context.
    judge_text = " ".join(str(m) for m in captured[0])
    assert "high-level programming language" in judge_text


# ---------------------------------------------------------------------------
# AC3 — contextual_relevancy
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_us031_ac3_contextual_relevancy():
    tc = EvaTestCase(
        id="tc-003",
        input="Explain RAG",
        retrieval_context="RAG stands for Retrieval-Augmented Generation.",
    )
    llm = make_mock_llm("0.9\nContext is highly relevant to the query.")
    ev = RAGContextualRelevancyEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt=tc.input,
        response="RAG combines retrieval with generation.",
        retrieval_context=tc.retrieval_context,
    )
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.9)
    assert score.metadata["evaluator_id"] == "contextual_relevancy"


# ---------------------------------------------------------------------------
# AC4 — contextual_precision
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_us031_ac4_contextual_precision():
    tc = EvaTestCase(
        id="tc-004",
        input="What is embeddings?",
        retrieval_context="Embeddings are vector representations of text.",
    )
    llm = make_mock_llm("0.8\nAll retrieved content is relevant.")
    ev = RAGContextualPrecisionEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt=tc.input,
        response="Embeddings map text to vectors.",
        retrieval_context=tc.retrieval_context,
    )
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.8)
    assert score.metadata["evaluator_id"] == "contextual_precision"


# ---------------------------------------------------------------------------
# AC5 — contextual_recall
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_us031_ac5_contextual_recall():
    tc = EvaTestCase(
        id="tc-005",
        input="What is LLM?",
        expected_output="LLM stands for Large Language Model.",
        retrieval_context="LLMs are large neural networks trained on text.",
    )
    llm = make_mock_llm("0.75\nContext covers most of expected output.")
    ev = RAGContextualRecallEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt=tc.input,
        response="LLMs are neural networks.",
        retrieval_context=tc.retrieval_context,
        expected_output=tc.expected_output,
    )
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.75)
    assert score.metadata["evaluator_id"] == "contextual_recall"


# ---------------------------------------------------------------------------
# AC6 — answer_relevancy
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_us031_ac6_answer_relevancy():
    tc = EvaTestCase(id="tc-006", input="What is FAISS?")
    llm = make_mock_llm("0.95\nResponse directly answers the question.")
    ev = RAGAnswerRelevancyEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt=tc.input,
        response="FAISS is a library for efficient similarity search.",
    )
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.95)
    assert score.metadata["evaluator_id"] == "answer_relevancy"


# ---------------------------------------------------------------------------
# AC7 — ragas composite averages + per-component breakdown
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_us031_ac7_ragas_composite_averages_and_breakdown():
    """Composite averages components and surfaces per-component scores."""

    def make_sub(name: str, val: float):
        class _Sub:
            evaluator_id = name

            async def evaluate(self, prompt, response, **_kw):
                return Score(
                    value=val,
                    reason=f"{name} mock",
                    metadata={"evaluator_id": self.evaluator_id},
                )

        return _Sub()

    sub_a = make_sub("faithfulness", 0.8)
    sub_b = make_sub("contextual_relevancy", 0.6)
    sub_c = make_sub("contextual_precision", 0.7)
    sub_d = make_sub("contextual_recall", 0.9)
    sub_e = make_sub("answer_relevancy", 1.0)

    ev = RAGASEvaluator(evaluators=[sub_a, sub_b, sub_c, sub_d, sub_e])
    score = await ev.evaluate(prompt="q", response="a")

    assert isinstance(score, Score)
    # average of [0.8, 0.6, 0.7, 0.9, 1.0] = 0.8
    assert score.value == pytest.approx(0.8)
    assert score.metadata["evaluator_id"] == "ragas"
    breakdown = score.metadata["component_scores"]
    assert breakdown == {
        "faithfulness": 0.8,
        "contextual_relevancy": 0.6,
        "contextual_precision": 0.7,
        "contextual_recall": 0.9,
        "answer_relevancy": 1.0,
    }


@pytest.mark.asyncio
async def test_us031_ac7_ragas_default_components_from_llm_adapter():
    """When constructed with just an llm_adapter, RAGAS wires the 4+1 defaults."""
    llm = make_mock_llm("0.5\nok")
    ev = RAGASEvaluator(llm_adapter=llm)
    # 5 default components: faithfulness, ctx_relevancy, ctx_precision, ctx_recall, answer_rel.
    assert len(ev.evaluators) == 5
    ids = {e.evaluator_id for e in ev.evaluators}
    assert ids == {
        "faithfulness",
        "contextual_relevancy",
        "contextual_precision",
        "contextual_recall",
        "answer_relevancy",
    }


# ---------------------------------------------------------------------------
# AC8 — graceful degradation across ALL RAG evaluators when retrieval_context absent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_us031_ac8_faithfulness_degrades_without_context():
    """RAGFaithfulnessEvaluator falls back to a general grounding judge prompt."""
    llm = make_mock_llm("0.7\nGeneral grounding looks reasonable.")
    ev = RAGFaithfulnessEvaluator(llm_adapter=llm)
    score = await ev.evaluate(prompt="What is Go?", response="Go is a compiled language.")
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.7)
    assert score.metadata["had_retrieval_context"] is False


@pytest.mark.asyncio
async def test_us031_ac8_contextual_relevancy_degrades_without_context():
    llm = make_mock_llm("nope")  # should not be called
    ev = RAGContextualRelevancyEvaluator(llm_adapter=llm)
    score = await ev.evaluate(prompt="q", response="r")
    assert isinstance(score, Score)
    assert score.metadata.get("fallback") is True
    llm.complete.assert_not_called()


@pytest.mark.asyncio
async def test_us031_ac8_contextual_precision_degrades_without_context():
    llm = make_mock_llm("nope")
    ev = RAGContextualPrecisionEvaluator(llm_adapter=llm)
    score = await ev.evaluate(prompt="q", response="r")
    assert isinstance(score, Score)
    assert score.metadata.get("fallback") is True
    llm.complete.assert_not_called()


@pytest.mark.asyncio
async def test_us031_ac8_contextual_recall_degrades_without_context():
    llm = make_mock_llm("nope")
    ev = RAGContextualRecallEvaluator(llm_adapter=llm, expected_output="x")
    score = await ev.evaluate(prompt="q", response="r")
    assert isinstance(score, Score)
    assert score.metadata.get("fallback") is True
    llm.complete.assert_not_called()


@pytest.mark.asyncio
async def test_us031_ac8_answer_relevancy_works_without_context():
    """Answer relevancy does not require retrieval context — still scores normally."""
    llm = make_mock_llm("0.9\nok")
    ev = RAGAnswerRelevancyEvaluator(llm_adapter=llm)
    score = await ev.evaluate(prompt="q", response="r")
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_us031_ac8_ragas_composite_degrades_without_context():
    """RAGAS composite still returns a Score; sub-evaluators fall back individually."""
    llm = make_mock_llm("0.4\nok")
    ev = RAGASEvaluator(llm_adapter=llm)
    score = await ev.evaluate(prompt="q", response="r")
    assert isinstance(score, Score)
    # Composite score still computed; per-component breakdown still present.
    assert "component_scores" in score.metadata
    assert len(score.metadata["component_scores"]) == 5
