# tests/unit/test_contract.py
import pytest
from pathlib import Path
from core.contract import load_contract, ContractValidationError

FIXTURES = Path("tests/fixtures/contracts")

def test_load_valid_contract():
    c = load_contract(FIXTURES / "valid.yaml")
    assert c.name == "refund_policy"
    assert c.provider == "billing-agent"
    assert c.consumer == "support-agent"
    assert len(c.evaluators) == 2
    assert c.retry_policy.max_retries == 3

def test_load_sets_defaults():
    c = load_contract(FIXTURES / "valid.yaml")
    assert c.retry_policy.backoff_ms == 0

def test_load_missing_name_raises():
    with pytest.raises(ContractValidationError, match="name"):
        load_contract(FIXTURES / "invalid_missing_name.yaml")

def test_load_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_contract(Path("does/not/exist.yaml"))
