# tests/server/test_registry.py
import pytest
from pathlib import Path
from server.contracts.registry import ContractRegistry

FIXTURES = Path("tests/fixtures/contracts")


def test_load_single_contract():
    registry = ContractRegistry()
    registry.load_file(FIXTURES / "echo_agent.yaml")
    contract = registry.get("echo_agent")
    assert contract is not None
    assert contract.name == "echo_agent"
    assert contract.provider == "echo-agent"


def test_get_missing_returns_none():
    registry = ContractRegistry()
    assert registry.get("does_not_exist") is None


def test_load_directory_loads_all_yaml():
    registry = ContractRegistry()
    registry.load_dir(FIXTURES)
    # fixtures dir has at least valid.yaml and echo_agent.yaml
    assert len(registry.all()) >= 2


def test_reload_updates_contract(tmp_path):
    import yaml
    contract_data = {
        "name": "dynamic",
        "provider": "agent-x",
        "request_schema": {"type": "object"},
        "evaluators": [],
        "retry_policy": {"max_retries": 1},
    }
    f = tmp_path / "dynamic.yaml"
    f.write_text(yaml.dump(contract_data))
    registry = ContractRegistry()
    registry.load_file(f)
    assert registry.get("dynamic").retry_policy.max_retries == 1

    # Update file and reload
    contract_data["retry_policy"]["max_retries"] = 5
    f.write_text(yaml.dump(contract_data))
    registry.load_file(f)
    assert registry.get("dynamic").retry_policy.max_retries == 5


def test_list_returns_all_names():
    registry = ContractRegistry()
    registry.load_file(FIXTURES / "echo_agent.yaml")
    names = registry.list_names()
    assert "echo_agent" in names
