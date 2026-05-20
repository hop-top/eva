# core/dataset.py
import json
from pathlib import Path
from pydantic import BaseModel
import yaml

from core.models import ConversationTestCase


class EvaTestCase(BaseModel):
    id: str
    input: str
    expected_output: str | None = None
    retrieval_context: str | None = None
    planned_steps: list[str] | None = None
    metadata: dict = {}


class Dataset(BaseModel):
    name: str
    target: str
    evaluators: list[dict] = []
    tests: list[EvaTestCase] = []


class ConversationDataset(BaseModel):
    name: str
    target: str
    evaluators: list[dict] = []
    tests: list[ConversationTestCase] = []


def load_dataset(path: Path, target: str | None = None) -> Dataset:
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    if path.suffix == ".jsonl":
        if not target:
            raise ValueError("target URL required when loading JSONL datasets")
        tests = []
        for line in path.read_text().splitlines():
            line = line.strip()
            if line:
                tests.append(EvaTestCase.model_validate(json.loads(line)))
        return Dataset(name=path.stem, target=target, tests=tests)

    raw = yaml.safe_load(path.read_text())
    if target:
        raw["target"] = target
    tests = [EvaTestCase.model_validate(t) for t in raw.pop("tests", [])]
    return Dataset(tests=tests, **raw)


def load_conversation_dataset(path: Path, target: str | None = None) -> ConversationDataset:
    """Load a YAML dataset with ``conversation: true`` flag into ConversationDataset."""
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    raw = yaml.safe_load(path.read_text())
    if target:
        raw["target"] = target
    raw.pop("conversation", None)
    tests = [ConversationTestCase.model_validate(t) for t in raw.pop("tests", [])]
    return ConversationDataset(tests=tests, **raw)
