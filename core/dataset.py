# core/dataset.py
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, model_validator
import yaml

from core.chat_targets import CHAT_PROVIDERS, ChatTarget
from core.models import ConversationTestCase


class EvaTestCase(BaseModel):
    id: str
    input: str
    expected_output: str | None = None
    retrieval_context: str | None = None
    planned_steps: list[str] | None = None
    # Unit-test code for the ``code_tests`` evaluator: one string or a list
    # of snippets (joined by newlines). Executed against the response's code.
    tests: str | list[str] | None = None
    # OpenAI-format tool definitions offered to a chat target for this case
    # (``[{"type": "function", "function": {name, description, parameters}}]``)
    # and the optional ``tool_choice`` ("auto" | "none" | "required" | a
    # ``{"type": "function", "function": {"name": ...}}`` mapping).
    tools: list[dict] | None = None
    tool_choice: str | dict | None = None
    metadata: dict = {}

    @model_validator(mode="after")
    def _tool_choice_needs_tools(self) -> "EvaTestCase":
        if self.tool_choice is not None and not self.tools:
            raise ValueError("tool_choice requires tools")
        return self


class Dataset(BaseModel):
    """Eval dataset.

    ``target`` is either a URL string (POST ``{"input": ...}``) or a chat
    target mapping (see core/chat_targets.py). In the mapping case ``chat``
    holds the parsed ChatTarget and ``target`` becomes its stable label
    (``provider:model@base_url``), which keys the run in the store.
    """

    name: str
    target: str
    chat: ChatTarget | None = None
    evaluators: list[dict] = []
    tests: list[EvaTestCase] = []

    @model_validator(mode="before")
    @classmethod
    def _chat_target(cls, data: Any) -> Any:
        if isinstance(data, dict) and isinstance(data.get("target"), dict):
            data = dict(data)
            chat = ChatTarget.model_validate(data["target"])
            if chat.provider not in CHAT_PROVIDERS:
                raise ValueError(
                    f"unknown chat provider {chat.provider!r}; "
                    f"known: {', '.join(sorted(CHAT_PROVIDERS))}"
                )
            data["chat"] = chat
            data["target"] = chat.label
        return data


class ConversationDataset(BaseModel):
    name: str
    target: str
    evaluators: list[dict] = []
    tests: list[ConversationTestCase] = []


def load_dataset(
    path: Path,
    target: str | None = None,
    chat: dict | None = None,
) -> Dataset:
    """Load a YAML/JSONL dataset.

    ``target``: URL override (replaces any dataset target, including a chat
    mapping). ``chat``: chat-target fields (provider, base_url, model, …)
    merged over the dataset's own ``target:`` mapping; a JSONL dataset has
    none, so ``chat`` must supply provider + model.
    """
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")
    if target and chat:
        raise ValueError("a URL target and chat target fields are mutually exclusive")
    chat = {k: v for k, v in (chat or {}).items() if v is not None}

    if path.suffix == ".jsonl":
        if not target and not chat:
            raise ValueError(
                "target URL (or chat target provider/model) required "
                "when loading JSONL datasets"
            )
        tests = []
        for line in path.read_text().splitlines():
            line = line.strip()
            if line:
                tests.append(EvaTestCase.model_validate(json.loads(line)))
        return Dataset.model_validate(
            {"name": path.stem, "target": target or chat, "tests": tests}
        )

    raw = yaml.safe_load(path.read_text())
    if target:
        raw["target"] = target
    elif chat:
        base = raw.get("target")
        raw["target"] = {**(base if isinstance(base, dict) else {}), **chat}
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
