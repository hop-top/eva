# core/dataset.py
import hashlib
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
    # stdin/stdout mode for ``code_tests``: a list of
    # ``{"stdin": str, "expected_stdout": str}``; the program runs once per pair.
    stdio: list[dict] | None = None
    metadata: dict = {}
    # Append-only datasets: id of an earlier case this one replaces. The
    # earlier case stays in the dataset but is no longer scored.
    supersedes: str | None = None


# Fields that define what a case asks and how it is scored. ``metadata`` is
# deliberately not part of the case hash (provenance may be corrected
# without invalidating stored results).
CASE_HASH_FIELDS = (
    "id", "input", "expected_output", "retrieval_context",
    "planned_steps", "tests", "supersedes",
)


def case_hash(case: "EvaTestCase | dict") -> str:
    """Content hash of one case: sha256 hex over canonical JSON.

    Canonical form: the ``CASE_HASH_FIELDS`` that are set (``None`` omitted,
    so new optional fields never change existing hashes), ``tests`` as one
    newline-joined string when given as a list, serialised with sorted keys,
    compact separators, ``ensure_ascii=False``, UTF-8. Depends on the case
    alone: adding or removing other cases never changes it.
    """
    if not isinstance(case, EvaTestCase):
        case = EvaTestCase.model_validate(case)
    data = case.model_dump(mode="json")
    canon = {k: data[k] for k in CASE_HASH_FIELDS if data.get(k) is not None}
    if isinstance(canon.get("tests"), list):
        canon["tests"] = "\n".join(canon["tests"])
    blob = json.dumps(canon, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()

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
    # Opt-in: cases are never edited or removed (see core/append_only.py).
    append_only: bool = False
    # Explicit identity for stored per-case results (see result_target_id).
    target_id: str | None = None

    def scored_tests(self) -> list[EvaTestCase]:
        """Cases that run and score: all of them, minus superseded ones
        when the dataset is append-only."""
        if not self.append_only:
            return list(self.tests)
        gone = {t.supersedes for t in self.tests if t.supersedes}
        return [t for t in self.tests if t.id not in gone]

    @property
    def result_target_id(self) -> str:
        """Identity of the target in per-case results, stable across
        machines: explicit ``target_id`` / chat ``id``, else ``provider:model``
        for chat targets (no base URL, no sampling), else the target URL."""
        if self.target_id:
            return self.target_id
        if self.chat is not None:
            return self.chat.id or f"{self.chat.provider}:{self.chat.model}"
        return self.target

    @model_validator(mode="after")
    def _reserved_evaluator_names(self) -> "Dataset":
        for ev in self.evaluators:
            if isinstance(ev, dict) and ev.get("name") == "target":
                raise ValueError(
                    "evaluator name 'target' is reserved (it marks upstream "
                    "errors); rename the evaluator"
                )
        return self

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
    target_id: str | None = None,
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

    if path.is_dir():
        raw, tests = read_directory(path)
        if target:
            raw["target"] = target
        elif chat:
            base = raw.get("target")
            raw["target"] = {**(base if isinstance(base, dict) else {}), **chat}
        if "target" not in raw:
            raise ValueError(
                "target URL (or chat target provider/model) required: "
                "set it in dataset.yaml or pass it on the command line"
            )
        return _with_id(Dataset(tests=tests, **raw), target_id)

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
        return _with_id(Dataset.model_validate(
            {"name": path.stem, "target": target or chat, "tests": tests}
        ), target_id)

    raw = yaml.safe_load(path.read_text())
    if target:
        raw["target"] = target
    elif chat:
        base = raw.get("target")
        raw["target"] = {**(base if isinstance(base, dict) else {}), **chat}
    tests = [EvaTestCase.model_validate(t) for t in raw.pop("tests", [])]
    return _with_id(Dataset(tests=tests, **raw), target_id)


def _with_id(ds: Dataset, target_id: str | None) -> Dataset:
    if target_id:
        ds.target_id = target_id
    return ds


MANIFEST_NAMES = ("dataset.yaml", "dataset.yml")


def read_directory(path: Path) -> tuple[dict, list[EvaTestCase]]:
    """Read a directory dataset: ``*.jsonl`` files (sorted by file name,
    lines in order) plus an optional ``dataset.yaml`` manifest holding
    name/target/evaluators/append_only. File names carry no meaning."""
    raw: dict = {}
    for name in MANIFEST_NAMES:
        if (path / name).exists():
            raw = yaml.safe_load((path / name).read_text()) or {}
            break
    raw.pop("tests", None)
    raw.setdefault("name", path.resolve().name)
    tests: list[EvaTestCase] = []
    for f in sorted(path.glob("*.jsonl")):
        for n, line in enumerate(f.read_text().splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                tests.append(EvaTestCase.model_validate(json.loads(line)))
            except ValueError as e:
                raise ValueError(f"{f.name}:{n}: {e}") from None
    return raw, tests


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
