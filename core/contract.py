# core/contract.py
from pathlib import Path
import yaml
from pydantic import ValidationError
from core.models import Contract


class ContractValidationError(Exception):
    pass


def _compile_assertions(raw: dict) -> dict:
    """Translate top-level `assertions: [...]` into prose_assertion EvaluatorRef
    entries appended to the contract's `evaluators` list.

    Each entry is either:

      - **A bare string** (default routing — programmatic-first, judge fallback):

            assertions:
              - "branch name does NOT contain 'worktree'"

      - **A dict with `text:` + optional override flags** (T-0380 mode override):

            assertions:
              - text: "uses imperative mood"
                judge: true                # force llm_judge
              - text: "starts with 'feat/'"
                programmatic_only: true    # fail at load if no rule matches

      ``judge: true`` maps to ``mode="judge_only"``;
      ``programmatic_only: true`` maps to ``mode="programmatic_only"``.
      Both flags at once is rejected (they're contradictory).

    Each assertion becomes one EvaluatorRef carrying ``assertion`` and
    optionally ``assertion_mode`` as pydantic extras (EvaluatorRef has
    ``extra="allow"``), which the factory in
    ``core/evaluators/builtin.py`` reads to construct the
    ``ProseAssertionEvaluator``.

    Mutates and returns the raw dict so callers don't need to thread a
    separate copy. Safe because `load_contract` already owns `raw`.
    """
    assertions = raw.get("assertions") or []
    if not assertions:
        return raw
    if not isinstance(assertions, list):
        raise ContractValidationError(
            "`assertions:` must be a list of strings or dicts (got "
            f"{type(assertions).__name__})"
        )
    raw.setdefault("evaluators", [])
    for entry in assertions:
        if isinstance(entry, str):
            text = entry
            mode = "auto"
        elif isinstance(entry, dict):
            text = entry.get("text")
            if not isinstance(text, str) or not text:
                raise ContractValidationError(
                    "dict assertion entry must have a non-empty `text:` field "
                    f"(got {entry!r})"
                )
            judge = bool(entry.get("judge", False))
            programmatic_only = bool(entry.get("programmatic_only", False))
            if judge and programmatic_only:
                raise ContractValidationError(
                    "assertion entry cannot set both `judge: true` and "
                    f"`programmatic_only: true` (got {entry!r})"
                )
            if judge:
                mode = "judge_only"
            elif programmatic_only:
                mode = "programmatic_only"
            else:
                mode = "auto"
        else:
            raise ContractValidationError(
                "every entry in `assertions:` must be a string or dict (got "
                f"{type(entry).__name__}: {entry!r})"
            )
        ref: dict = {
            "name": "prose_assertion",
            "mode": "binary",
            "assertion": text,
        }
        if mode != "auto":
            ref["assertion_mode"] = mode
        raw["evaluators"].append(ref)
    # `assertions` is consumed by the loader; drop so it doesn't leak
    # through pydantic extra-allow on Contract (which ignores unknowns).
    raw.pop("assertions", None)
    return raw


def load_contract(path: Path) -> Contract:
    if not path.exists():
        raise FileNotFoundError(f"Contract file not found: {path}")
    raw = yaml.safe_load(path.read_text())
    if not raw or "name" not in raw:
        raise ContractValidationError("Contract must have a 'name' field")
    raw = _compile_assertions(raw)
    try:
        return Contract.model_validate(raw)
    except ValidationError as e:
        raise ContractValidationError(str(e)) from e
