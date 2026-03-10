"""Unit tests for eva-a2a importer."""
import json
import pytest
from pathlib import Path

FIXTURES = Path(__file__).parent.parent.parent / "plugins/eva-a2a/tests/fixtures"


def test_import_produces_contracts_per_skill():
    from eva_a2a.importer import import_agent_card
    card = json.loads((FIXTURES / "billing_agent_card.json").read_text())
    contracts = import_agent_card(card)
    assert len(contracts) == 2


def test_import_contract_names():
    from eva_a2a.importer import import_agent_card
    card = json.loads((FIXTURES / "billing_agent_card.json").read_text())
    contracts = import_agent_card(card)
    names = [c.name for c in contracts]
    assert "billing-agent.process_refund" in names
    assert "billing-agent.get_invoice" in names


def test_import_sets_provider():
    from eva_a2a.importer import import_agent_card
    card = json.loads((FIXTURES / "billing_agent_card.json").read_text())
    contracts = import_agent_card(card)
    for c in contracts:
        assert c.provider == "billing-agent"


def test_import_missing_name_raises():
    from eva_a2a.importer import import_agent_card, A2AImportError
    with pytest.raises(A2AImportError, match="name"):
        import_agent_card({"skills": []})


def test_import_skill_without_schema_uses_empty():
    from eva_a2a.importer import import_agent_card
    card = {"name": "simple-agent", "skills": [{"name": "ping"}]}
    contracts = import_agent_card(card)
    assert contracts[0].request_schema == {}


def test_contracts_to_yaml(tmp_path):
    from eva_a2a.importer import import_agent_card, contracts_to_yaml
    import yaml
    card = json.loads((FIXTURES / "billing_agent_card.json").read_text())
    contracts = import_agent_card(card)
    paths = contracts_to_yaml(contracts, tmp_path / "out")
    assert len(paths) == 2
    for p in paths:
        data = yaml.safe_load(p.read_text())
        assert data["provider"] == "billing-agent"
