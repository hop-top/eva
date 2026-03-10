import json
import pytest
from pathlib import Path
from eva_a2a.importer import import_agent_card, contracts_to_yaml, A2AImportError

FIXTURES = Path(__file__).parent / "fixtures"


def test_import_produces_contracts_per_skill():
    card = json.loads((FIXTURES / "billing_agent_card.json").read_text())
    contracts = import_agent_card(card)
    assert len(contracts) == 2  # one per skill


def test_import_contract_names():
    card = json.loads((FIXTURES / "billing_agent_card.json").read_text())
    contracts = import_agent_card(card)
    names = [c.name for c in contracts]
    assert "billing-agent.process_refund" in names
    assert "billing-agent.get_invoice" in names


def test_import_preserves_request_schema():
    card = json.loads((FIXTURES / "billing_agent_card.json").read_text())
    contracts = import_agent_card(card)
    refund = next(c for c in contracts if "process_refund" in c.name)
    assert refund.request_schema["required"] == ["order_id"]
    assert "order_id" in refund.request_schema["properties"]


def test_import_sets_provider():
    card = json.loads((FIXTURES / "billing_agent_card.json").read_text())
    contracts = import_agent_card(card)
    for c in contracts:
        assert c.provider == "billing-agent"


def test_import_missing_name_raises():
    with pytest.raises(A2AImportError, match="name"):
        import_agent_card({"skills": []})


def test_import_skill_without_input_schema_uses_empty():
    card = {
        "name": "simple-agent",
        "skills": [{"name": "do_thing", "description": "Does a thing"}],
    }
    contracts = import_agent_card(card)
    assert contracts[0].request_schema == {}


def test_to_yaml_produces_valid_files(tmp_path):
    card = json.loads((FIXTURES / "billing_agent_card.json").read_text())
    contracts = import_agent_card(card)
    paths = contracts_to_yaml(contracts, tmp_path / "out")
    assert len(paths) == 2
    for p in paths:
        assert p.exists()
        import yaml
        data = yaml.safe_load(p.read_text())
        assert "name" in data
        assert "provider" in data
        assert data["provider"] == "billing-agent"
