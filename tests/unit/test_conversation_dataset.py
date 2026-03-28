# tests/unit/test_conversation_dataset.py
import pytest
import tempfile
from pathlib import Path
from pydantic import ValidationError

from core.models import Turn, ConversationTestCase
from core.dataset import ConversationDataset, load_conversation_dataset


SAMPLE_YAML = """\
name: my-conv-dataset
target: http://localhost:8000/chat
conversation: true
tests:
  - id: tc-001
    turns:
      - role: user
        content: What is your name?
      - role: assistant
        content: My name is Eva.
      - role: user
        content: How old are you?
    expected_output: I am a new assistant.
"""


# ---------------------------------------------------------------------------
# Turn model
# ---------------------------------------------------------------------------

def test_turn_valid_user():
    t = Turn(role="user", content="Hello")
    assert t.role == "user"
    assert t.content == "Hello"


def test_turn_valid_assistant():
    t = Turn(role="assistant", content="Hi there")
    assert t.role == "assistant"


def test_turn_invalid_role():
    with pytest.raises(ValidationError):
        Turn(role="system", content="You are a bot")


# ---------------------------------------------------------------------------
# ConversationTestCase
# ---------------------------------------------------------------------------

def test_conversation_test_case_parses_turns():
    raw = {
        "id": "tc-001",
        "turns": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ],
        "expected_output": "Hi",
    }
    tc = ConversationTestCase.model_validate(raw)
    assert tc.id == "tc-001"
    assert len(tc.turns) == 2
    assert tc.turns[0].role == "user"
    assert tc.turns[1].role == "assistant"
    assert tc.expected_output == "Hi"


def test_conversation_test_case_defaults():
    tc = ConversationTestCase(id="x", turns=[])
    assert tc.expected_output is None
    assert tc.metadata == {}


# ---------------------------------------------------------------------------
# load_conversation_dataset
# ---------------------------------------------------------------------------

def test_load_conversation_dataset_from_yaml():
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        f.write(SAMPLE_YAML)
        tmp = Path(f.name)

    try:
        ds = load_conversation_dataset(tmp)
        assert ds.name == "my-conv-dataset"
        assert ds.target == "http://localhost:8000/chat"
        assert len(ds.tests) == 1
        tc = ds.tests[0]
        assert tc.id == "tc-001"
        assert len(tc.turns) == 3
        assert tc.turns[0].role == "user"
        assert tc.turns[1].role == "assistant"
        assert tc.expected_output == "I am a new assistant."
    finally:
        tmp.unlink()


def test_load_conversation_dataset_target_override():
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        f.write(SAMPLE_YAML)
        tmp = Path(f.name)

    try:
        ds = load_conversation_dataset(tmp, target="http://override/api")
        assert ds.target == "http://override/api"
    finally:
        tmp.unlink()


def test_load_conversation_dataset_not_found():
    with pytest.raises(FileNotFoundError):
        load_conversation_dataset(Path("/nonexistent/path.yaml"))
