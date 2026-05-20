# tests/e2e/test_multi_turn_evaluators.py
"""E2E tests: multi-turn evaluators + ConversationDataset loading."""
from pathlib import Path
import pytest
import yaml
from unittest.mock import AsyncMock, MagicMock

from core.dataset import ConversationDataset, load_conversation_dataset
from core.evaluators.llm_judge import (
    ConversationCompletenessEvaluator,
    KnowledgeRetentionEvaluator,
    RoleAdherenceEvaluator,
    TurnFaithfulnessEvaluator,
    TurnRelevancyEvaluator,
)
from core.models import ConversationTestCase, Score, Turn


def make_mock_llm(reply: str) -> AsyncMock:
    mock = AsyncMock()
    completion = MagicMock()
    completion.content = reply
    mock.complete = AsyncMock(return_value=completion)
    return mock


HISTORY_2 = [
    {"role": "user", "content": "My name is Alice."},
    {"role": "assistant", "content": "Nice to meet you, Alice."},
]


# ---------------------------------------------------------------------------
# ConversationDataset loading
# ---------------------------------------------------------------------------

def test_conversation_dataset_loads_turns(tmp_path: Path):
    yaml_content = """
name: conv-test
target: http://localhost:9999
conversation: true
tests:
  - id: conv-001
    turns:
      - role: user
        content: Hello
      - role: assistant
        content: Hi there
"""
    ds_file = tmp_path / "conv_dataset.yaml"
    ds_file.write_text(yaml_content)

    dataset = load_conversation_dataset(ds_file)
    assert len(dataset.tests) == 1
    tc = dataset.tests[0]
    assert isinstance(tc, ConversationTestCase)
    assert len(tc.turns) == 2
    assert tc.turns[0].role == "user"
    assert tc.turns[0].content == "Hello"


# ---------------------------------------------------------------------------
# KnowledgeRetentionEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_knowledge_retention_with_history():
    llm = make_mock_llm("0.9\nAgent recalled the user's name correctly.")
    ev = KnowledgeRetentionEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt="What is my name?",
        response="Your name is Alice.",
        conversation_history=HISTORY_2,
    )
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# ConversationCompletenessEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_conversation_completeness():
    llm = make_mock_llm("0.8\nAll user requests addressed.")
    ev = ConversationCompletenessEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt="Wrap up conversation",
        response="I have answered all your questions.",
        conversation_history=HISTORY_2,
    )
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# TurnRelevancyEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_turn_relevancy():
    llm = make_mock_llm("0.85\nResponse is on-topic.")
    ev = TurnRelevancyEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt="What is the capital of France?",
        response="The capital of France is Paris.",
    )
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.85)


# ---------------------------------------------------------------------------
# TurnFaithfulnessEvaluator - with retrieval_context
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_turn_faithfulness_with_retrieval():
    llm = make_mock_llm("0.95\nAll claims grounded in context.")
    ev = TurnFaithfulnessEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt="Tell me about Paris.",
        response="Paris is the capital of France and a major cultural hub.",
        conversation_history=HISTORY_2,
        retrieval_context="Paris is the capital city of France, known for art and culture.",
    )
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.95)


# ---------------------------------------------------------------------------
# RoleAdherenceEvaluator - persona in prompt
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_role_adherence_custom_persona():
    captured_messages = []

    async def capturing_complete(messages):
        captured_messages.extend(messages)
        c = MagicMock()
        c.content = "0.9\nAria persona maintained."
        return c

    mock_llm = MagicMock()
    mock_llm.complete = capturing_complete

    ev = RoleAdherenceEvaluator(llm_adapter=mock_llm, persona="Aria")
    score = await ev.evaluate(
        prompt="Introduce yourself",
        response="Hello! I am Aria, your AI assistant.",
        conversation_history=HISTORY_2,
    )

    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.9)
    combined = " ".join(str(m) for m in captured_messages)
    assert "Aria" in combined


# ---------------------------------------------------------------------------
# ConversationDataset YAML round-trip
# ---------------------------------------------------------------------------

def test_conversation_yaml_roundtrip(tmp_path: Path):
    original = ConversationDataset(
        name="roundtrip",
        target="http://localhost:9999",
        tests=[
            ConversationTestCase(
                id="rt-001",
                turns=[
                    Turn(role="user", content="Hello"),
                    Turn(role="assistant", content="Hi"),
                ],
            )
        ],
    )

    raw = original.model_dump()
    yaml_str = yaml.dump(raw)

    ds_file = tmp_path / "roundtrip.yaml"
    ds_file.write_text(yaml_str)

    loaded_raw = yaml.safe_load(ds_file.read_text())
    loaded = ConversationDataset.model_validate(loaded_raw)

    assert loaded.name == "roundtrip"
    assert len(loaded.tests) == 1
    assert len(loaded.tests[0].turns) == 2
    assert loaded.tests[0].turns[0].content == "Hello"
    assert loaded.tests[0].turns[1].content == "Hi"
