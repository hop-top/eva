# tests/unit/test_evaluator_ref_extras.py
# Regression tests for T-0260: EvaluatorRef must preserve per-evaluator config
# fields (substring/pattern/schema/…) instead of stripping them on load.
from pathlib import Path

import yaml

from core.contract import load_contract
from core.models import Contract, EvaluatorRef


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


# --- direct model construction ------------------------------------------------


def test_evaluator_ref_preserves_substring():
    ref = EvaluatorRef(name="contains", substring="foo", case_sensitive=False)
    assert ref.substring == "foo"
    assert ref.case_sensitive is False


def test_evaluator_ref_preserves_pattern():
    ref = EvaluatorRef(name="regex", pattern="^hello")
    assert ref.pattern == "^hello"


def test_evaluator_ref_preserves_schema():
    # NOTE: `schema` shadows BaseModel.schema() (deprecated method) so it's not
    # safely reachable as an attribute. Consumers must read it via the extras
    # dict (`__pydantic_extra__`) or `model_dump()`. The gateway already does
    # the former (see server/gateway/routes.py:_build_evaluator_map call site).
    schema = {"type": "object", "required": ["ok"]}
    ref = EvaluatorRef(name="json_schema_valid", schema=schema)
    assert (ref.__pydantic_extra__ or {}).get("schema") == schema
    assert ref.model_dump()["schema"] == schema


def test_evaluator_ref_without_extras_still_works():
    ref = EvaluatorRef(name="no_pii")
    assert ref.name == "no_pii"
    assert ref.mode == "binary"
    assert ref.min_score == 1.0
    # No extras present → __pydantic_extra__ is empty (or None)
    assert not (ref.__pydantic_extra__ or {})


def test_evaluator_ref_extras_in_pydantic_extra():
    ref = EvaluatorRef(name="contains", substring="foo")
    extras = ref.__pydantic_extra__ or {}
    assert extras.get("substring") == "foo"


# --- contract YAML round-trip -------------------------------------------------


def test_load_contract_preserves_evaluator_extras():
    contract = load_contract(FIXTURES / "contracts" / "with_evaluator_config.yaml")
    by_name = {e.name: e for e in contract.evaluators}

    assert by_name["contains"].substring == "foo"
    assert by_name["contains"].case_sensitive is False
    assert by_name["regex"].pattern == "^hello"
    # `schema` shadowed by BaseModel.schema() — see note in
    # test_evaluator_ref_preserves_schema.
    assert (by_name["json_schema_valid"].__pydantic_extra__ or {}).get(
        "schema"
    ) == {"type": "object", "required": ["ok"]}


def test_load_existing_contract_without_extras_still_works():
    # Sanity: pre-existing fixture has no per-evaluator config → must not regress.
    contract = load_contract(FIXTURES / "contracts" / "valid.yaml")
    assert len(contract.evaluators) == 2
    for ev in contract.evaluators:
        assert ev.mode == "binary"


def test_contract_serialization_round_trip_preserves_extras():
    src = load_contract(FIXTURES / "contracts" / "with_evaluator_config.yaml")
    dumped = src.model_dump()
    rebuilt = Contract.model_validate(dumped)

    by_name = {e.name: e for e in rebuilt.evaluators}
    assert by_name["contains"].substring == "foo"
    assert by_name["regex"].pattern == "^hello"
    assert (by_name["json_schema_valid"].__pydantic_extra__ or {}).get(
        "schema"
    ) == {"type": "object", "required": ["ok"]}


def test_contract_yaml_dump_round_trip_preserves_extras():
    src = load_contract(FIXTURES / "contracts" / "with_evaluator_config.yaml")
    raw = yaml.safe_dump(src.model_dump())
    parsed = yaml.safe_load(raw)
    rebuilt = Contract.model_validate(parsed)

    by_name = {e.name: e for e in rebuilt.evaluators}
    assert by_name["contains"].substring == "foo"
    assert by_name["regex"].pattern == "^hello"
