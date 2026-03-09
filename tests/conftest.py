# tests/conftest.py
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
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


# ------------------------------------------------------------------ #
# Phase 2 fixtures                                                      #
# ------------------------------------------------------------------ #


@pytest.fixture
def mock_litellm():
    """Patch litellm.acompletion; response has score + reason in content."""
    choice = MagicMock()
    choice.message.content = "0.8\nReason: test"
    response = MagicMock()
    response.choices = [choice]

    async def _acompletion(*args, **kwargs):
        return response

    with patch("litellm.acompletion", side_effect=_acompletion) as m:
        yield m


@pytest.fixture
def mock_redis():
    """AsyncMock implementing the StateAdapter interface (get/set/delete)."""
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=None)
    mock.delete = AsyncMock(return_value=None)
    return mock


@pytest.fixture
def otel_noop():
    """Return a NoopOtelAdapter instance."""
    try:
        from core.otel import NoopOtelAdapter

        return NoopOtelAdapter()
    except ImportError:
        pytest.skip("core.otel not available")
