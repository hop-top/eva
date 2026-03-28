# tests/unit/test_multi_turn_evaluators.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from core.evaluators.llm_judge import (
    KnowledgeRetentionEvaluator,
    ConversationCompletenessEvaluator,
    TurnRelevancyEvaluator,
    TurnFaithfulnessEvaluator,
    RoleAdherenceEvaluator,
)
from core.models import Score


def make_mock_llm(reply: str) -> AsyncMock:
    mock = AsyncMock()
    completion = MagicMock()
    completion.content = reply
    mock.complete = AsyncMock(return_value=completion)
    return mock


HISTORY = [
    {"role": "user", "content": "My name is Alice and I live in Paris."},
    {"role": "assistant", "content": "Nice to meet you, Alice!"},
    {"role": "user", "content": "What city do I live in?"},
]


# ---------------------------------------------------------------------------
# KnowledgeRetentionEvaluator (T-0180)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_knowledge_retention_high_score():
    llm = make_mock_llm("0.95\nAgent correctly recalled that the user lives in Paris.")
    ev = KnowledgeRetentionEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt="What city do I live in?",
        response="You live in Paris.",
        conversation_history=HISTORY,
    )
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.95)
    assert score.metadata["evaluator_id"] == "knowledge_retention"
    content = llm.complete.call_args[0][0][0]["content"]
    assert "Paris" in content


@pytest.mark.asyncio
async def test_knowledge_retention_low_score():
    llm = make_mock_llm("0.1\nAgent contradicted earlier information by saying London.")
    ev = KnowledgeRetentionEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt="What city do I live in?",
        response="You live in London.",
        conversation_history=HISTORY,
    )
    assert score.value == pytest.approx(0.1)
    assert "contradicted" in score.reason


# ---------------------------------------------------------------------------
# ConversationCompletenessEvaluator (T-0181)
# ---------------------------------------------------------------------------

COMPLETENESS_HISTORY = [
    {"role": "user", "content": "What is the capital of France? Also, what is 2+2?"},
    {"role": "assistant", "content": "The capital of France is Paris."},
]


@pytest.mark.asyncio
async def test_conversation_completeness_high_score():
    llm = make_mock_llm("0.9\nBoth user requests were addressed.")
    ev = ConversationCompletenessEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt="What is 2+2?",
        response="The capital of France is Paris. Also, 2+2 equals 4.",
        conversation_history=COMPLETENESS_HISTORY,
    )
    assert score.value == pytest.approx(0.9)
    assert score.metadata["evaluator_id"] == "conversation_completeness"


@pytest.mark.asyncio
async def test_conversation_completeness_low_score():
    llm = make_mock_llm("0.3\nOnly one of the two user requests was answered.")
    ev = ConversationCompletenessEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt="What is 2+2?",
        response="The capital of France is Paris.",
        conversation_history=COMPLETENESS_HISTORY,
    )
    assert score.value == pytest.approx(0.3)


# ---------------------------------------------------------------------------
# TurnRelevancyEvaluator (T-0182)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_turn_relevancy_high_score():
    llm = make_mock_llm("0.92\nResponse directly addresses the question about Python.")
    ev = TurnRelevancyEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt="What is Python?",
        response="Python is a high-level programming language.",
    )
    assert score.value == pytest.approx(0.92)
    assert score.metadata["evaluator_id"] == "turn_relevancy"
    content = llm.complete.call_args[0][0][0]["content"]
    assert "What is Python?" in content


@pytest.mark.asyncio
async def test_turn_relevancy_low_score():
    llm = make_mock_llm("0.05\nResponse is completely off-topic.")
    ev = TurnRelevancyEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt="What is Python?",
        response="The weather today is sunny.",
    )
    assert score.value == pytest.approx(0.05)


# ---------------------------------------------------------------------------
# TurnFaithfulnessEvaluator (T-0183)
# ---------------------------------------------------------------------------

FAITH_HISTORY = [
    {"role": "user", "content": "Tell me about the Eiffel Tower."},
    {"role": "assistant", "content": "The Eiffel Tower is in Paris, built in 1889."},
]


@pytest.mark.asyncio
async def test_turn_faithfulness_high_score():
    llm = make_mock_llm("0.88\nClaims are consistent with the retrieved context.")
    ev = TurnFaithfulnessEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt="How tall is it?",
        response="The Eiffel Tower is 330 metres tall.",
        conversation_history=FAITH_HISTORY,
        retrieval_context="The Eiffel Tower stands 330 metres (1,083 ft) tall.",
    )
    assert score.value == pytest.approx(0.88)
    assert score.metadata["evaluator_id"] == "turn_faithfulness"
    content = llm.complete.call_args[0][0][0]["content"]
    assert "330 metres" in content


@pytest.mark.asyncio
async def test_turn_faithfulness_low_score():
    llm = make_mock_llm("0.15\nResponse contradicts retrieved context about the height.")
    ev = TurnFaithfulnessEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt="How tall is it?",
        response="The Eiffel Tower is 500 metres tall.",
        conversation_history=FAITH_HISTORY,
        retrieval_context="The Eiffel Tower stands 330 metres (1,083 ft) tall.",
    )
    assert score.value == pytest.approx(0.15)


# ---------------------------------------------------------------------------
# RoleAdherenceEvaluator (T-0184)
# ---------------------------------------------------------------------------

ROLE_HISTORY = [
    {"role": "user", "content": "Hello!"},
    {"role": "assistant", "content": "Ahoy, matey! What can I help ye with?"},
    {"role": "user", "content": "What is the weather?"},
]


@pytest.mark.asyncio
async def test_role_adherence_default_persona():
    llm = make_mock_llm("0.85\nAssistant maintained a helpful tone throughout.")
    ev = RoleAdherenceEvaluator(llm_adapter=llm)
    assert ev.persona == "assistant"
    score = await ev.evaluate(
        prompt="What is the weather?",
        response="I can help with that!",
        conversation_history=ROLE_HISTORY,
    )
    assert score.value == pytest.approx(0.85)
    assert score.metadata["evaluator_id"] == "role_adherence"
    content = llm.complete.call_args[0][0][0]["content"]
    assert "'assistant'" in content


@pytest.mark.asyncio
async def test_role_adherence_custom_persona():
    llm = make_mock_llm("0.95\nPirate persona maintained consistently.")
    ev = RoleAdherenceEvaluator(llm_adapter=llm, persona="pirate")
    assert ev.persona == "pirate"
    score = await ev.evaluate(
        prompt="What is the weather?",
        response="Arrr, the seas be calm today, matey!",
        conversation_history=ROLE_HISTORY,
    )
    assert score.value == pytest.approx(0.95)
    content = llm.complete.call_args[0][0][0]["content"]
    assert "'pirate'" in content
