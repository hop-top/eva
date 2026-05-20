# tests/e2e/test_prose_assertion_evaluator.py
"""End-to-end: a YAML contract with `assertions: ["...", "..."]` compiles
through `load_contract` → routes through `evaluate_contract` →
ContractRunReport.

Because `core/evaluators/builtin.py` is NOT edited by this track (per the
multi-agent guardrail; see REGISTRY_ADDITIONS_agent_e.md), the e2e
test monkeypatches `BUILTIN_EVALUATOR_FACTORIES` to register
`prose_assertion` for the duration of the test — mirroring exactly what
the integrator will fold in at merge time.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from cli.run_contract import evaluate_contract
from core.contract import ContractValidationError, load_contract
from core.evaluators.builtin import BUILTIN_EVALUATOR_FACTORIES
from core.evaluators.prose_assertion import ProseAssertionEvaluator


# ---------------------------------------------------------------------------
# Fixtures: isolate cache + register prose_assertion in the builtin registry
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    yield


@pytest.fixture(autouse=True)
def register_prose_assertion(monkeypatch):
    """Register the prose_assertion factory in BUILTIN_EVALUATOR_FACTORIES
    for the duration of the test. Mirrors what the integrator will fold in
    when this track merges (see REGISTRY_ADDITIONS_agent_e.md).
    """
    factory = lambda cfg, llm: ProseAssertionEvaluator(
        assertion=cfg.get("assertion", ""),
        llm_adapter=llm if llm is not None else cfg.get("llm_adapter"),
    )
    monkeypatch.setitem(BUILTIN_EVALUATOR_FACTORIES, "prose_assertion", factory)
    yield


# ---------------------------------------------------------------------------
# Contract YAML fixtures (inline, written to tmp_path)
# ---------------------------------------------------------------------------


def _write_contract(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "contract.yaml"
    p.write_text(body)
    return p


# ---------------------------------------------------------------------------
# Loader translation
# ---------------------------------------------------------------------------


def test_assertions_list_translates_into_prose_assertion_refs(tmp_path):
    contract_path = _write_contract(
        tmp_path,
        """
name: cc-skills-branch-naming
provider: branch-namer
assertions:
  - "branch name does NOT contain 'worktree'"
  - "branch name starts with 'feat/'"
""",
    )
    contract = load_contract(contract_path)
    assert len(contract.evaluators) == 2
    assert {ref.name for ref in contract.evaluators} == {"prose_assertion"}
    assertions = [
        ref.__pydantic_extra__.get("assertion") for ref in contract.evaluators
    ]
    assert "branch name does NOT contain 'worktree'" in assertions
    assert "branch name starts with 'feat/'" in assertions


def test_assertions_can_coexist_with_existing_evaluators(tmp_path):
    contract_path = _write_contract(
        tmp_path,
        """
name: mixed
provider: writer
evaluators:
  - name: word_count
    mode: binary
    max: 100
assertions:
  - "response contains 'refund'"
""",
    )
    contract = load_contract(contract_path)
    names = [ref.name for ref in contract.evaluators]
    assert names == ["word_count", "prose_assertion"]


def test_invalid_assertions_field_raises(tmp_path):
    from core.contract import ContractValidationError

    contract_path = _write_contract(
        tmp_path,
        """
name: bad
provider: x
assertions: "this is a string not a list"
""",
    )
    with pytest.raises(ContractValidationError, match="must be a list"):
        load_contract(contract_path)


def test_non_string_assertion_entry_raises(tmp_path):
    from core.contract import ContractValidationError

    contract_path = _write_contract(
        tmp_path,
        """
name: bad
provider: x
assertions:
  - 42
""",
    )
    with pytest.raises(ContractValidationError, match="must be a string"):
        load_contract(contract_path)


# ---------------------------------------------------------------------------
# Full path: assertions in YAML → evaluate_contract → pass/fail
# ---------------------------------------------------------------------------


def test_pack_with_assertions_passes_when_response_satisfies_all(tmp_path):
    contract_path = _write_contract(
        tmp_path,
        """
name: cc-skills-branch-naming
provider: branch-namer
assertions:
  - "branch name does NOT contain 'worktree'"
  - "branch name starts with 'feat/'"
""",
    )
    report = evaluate_contract(contract_path, "feat/oauth-login")
    assert report.skipped == []
    assert report.passed is True
    assert len(report.outcomes) == 2
    assert all(o.passed for o in report.outcomes)


def test_pack_with_assertions_fails_when_negated_assertion_violated(tmp_path):
    contract_path = _write_contract(
        tmp_path,
        """
name: cc-skills-branch-naming
provider: branch-namer
assertions:
  - "branch name does NOT contain 'worktree'"
  - "branch name starts with 'feat/'"
""",
    )
    report = evaluate_contract(contract_path, "feat/worktree-oauth-login")
    assert report.skipped == []
    assert report.passed is False
    # The negated 'does NOT contain worktree' must be the failing outcome.
    failing = [o for o in report.outcomes if not o.passed]
    assert len(failing) == 1
    assert "worktree" in (failing[0].reason or "").lower() or "negated" in (failing[0].reason or "").lower()


def test_pack_with_assertions_fails_when_prefix_assertion_violated(tmp_path):
    contract_path = _write_contract(
        tmp_path,
        """
name: cc-skills-branch-naming
provider: branch-namer
assertions:
  - "branch name starts with 'feat/'"
""",
    )
    report = evaluate_contract(contract_path, "fix/login-crash")
    assert report.skipped == []
    assert report.passed is False
    assert len(report.outcomes) == 1
    assert report.outcomes[0].passed is False


def test_assertions_use_cache_across_repeated_compiles(tmp_path):
    """Compiling the same assertion twice (via two contract loads) must hit
    the cache on the second compile — proves determinism end-to-end."""
    contract_path = _write_contract(
        tmp_path,
        """
name: same
provider: x
assertions:
  - "response contains 'refund'"
""",
    )
    r1 = evaluate_contract(contract_path, "Your refund is processed")
    r2 = evaluate_contract(contract_path, "Your refund is processed")
    assert r1.passed is True
    assert r2.passed is True
    # Both runs must produce the same outcome shape (deterministic).
    assert [(o.name, o.score, o.passed) for o in r1.outcomes] == [
        (o.name, o.score, o.passed) for o in r2.outcomes
    ]


def test_empty_assertions_list_is_noop(tmp_path):
    contract_path = _write_contract(
        tmp_path,
        """
name: empty
provider: x
assertions: []
evaluators:
  - name: word_count
    mode: binary
    max: 10
""",
    )
    contract = load_contract(contract_path)
    assert len(contract.evaluators) == 1
    assert contract.evaluators[0].name == "word_count"


# ---------------------------------------------------------------------------
# T-0380: dict-shaped assertions with per-entry mode override
# ---------------------------------------------------------------------------


def test_dict_assertion_default_is_auto(tmp_path):
    """A dict entry with only `text:` and no override flags routes as auto.

    Loader should produce an EvaluatorRef WITHOUT `assertion_mode` in extras
    so the evaluator defaults to mode='auto' at construction.
    """
    contract_path = _write_contract(
        tmp_path,
        """
name: dict-default
provider: x
assertions:
  - text: "response contains 'foo'"
""",
    )
    contract = load_contract(contract_path)
    assert len(contract.evaluators) == 1
    ref = contract.evaluators[0]
    assert ref.name == "prose_assertion"
    assert ref.__pydantic_extra__.get("assertion") == "response contains 'foo'"
    # No mode override means no assertion_mode key — evaluator defaults to auto.
    assert "assertion_mode" not in (ref.__pydantic_extra__ or {})


def test_dict_assertion_judge_true_sets_judge_only_mode(tmp_path):
    contract_path = _write_contract(
        tmp_path,
        """
name: dict-judge
provider: x
assertions:
  - text: "uses imperative mood"
    judge: true
""",
    )
    contract = load_contract(contract_path)
    ref = contract.evaluators[0]
    assert ref.__pydantic_extra__.get("assertion_mode") == "judge_only"


def test_dict_assertion_programmatic_only_sets_mode(tmp_path):
    contract_path = _write_contract(
        tmp_path,
        """
name: dict-prog
provider: x
assertions:
  - text: "response contains 'foo'"
    programmatic_only: true
""",
    )
    contract = load_contract(contract_path)
    ref = contract.evaluators[0]
    assert ref.__pydantic_extra__.get("assertion_mode") == "programmatic_only"


def test_dict_assertion_both_flags_raises(tmp_path):
    contract_path = _write_contract(
        tmp_path,
        """
name: dict-bad
provider: x
assertions:
  - text: "anything"
    judge: true
    programmatic_only: true
""",
    )
    with pytest.raises(ContractValidationError, match="cannot set both"):
        load_contract(contract_path)


def test_dict_assertion_missing_text_raises(tmp_path):
    contract_path = _write_contract(
        tmp_path,
        """
name: dict-bad
provider: x
assertions:
  - judge: true
""",
    )
    with pytest.raises(ContractValidationError, match="`text:`"):
        load_contract(contract_path)


def test_dict_assertion_mixed_with_bare_strings(tmp_path):
    """Bare strings and dict entries coexist in one assertions: block."""
    contract_path = _write_contract(
        tmp_path,
        """
name: mixed
provider: x
assertions:
  - "response contains 'foo'"
  - text: "uses imperative mood"
    judge: true
  - text: "response contains 'bar'"
    programmatic_only: true
""",
    )
    contract = load_contract(contract_path)
    assert len(contract.evaluators) == 3
    modes = [
        ref.__pydantic_extra__.get("assertion_mode") for ref in contract.evaluators
    ]
    # First (bare string) has no mode key; second is judge_only; third programmatic_only.
    assert modes == [None, "judge_only", "programmatic_only"]
