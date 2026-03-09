# tests/conftest.py
import pytest
from pathlib import Path
from core.contract import load_contract
from core.dataset import load_dataset
from core.storage import SqliteStorage

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def contract_fixture():
    """Load the canonical valid contract fixture."""
    return load_contract(FIXTURES / "contracts" / "valid.yaml")


@pytest.fixture
def dataset_fixture():
    """Load the canonical simple YAML dataset fixture."""
    return load_dataset(FIXTURES / "datasets" / "simple.yaml")


@pytest.fixture
def sqlite_storage():
    """Return an in-memory SQLite storage instance (no disk I/O)."""
    return SqliteStorage(db_url="sqlite:///:memory:")
