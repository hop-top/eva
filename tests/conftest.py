# tests/conftest.py
import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="Run tests that require external services (Postgres, Redis, etc.)",
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--integration"):
        skip = pytest.mark.skip(reason="Pass --integration to run integration tests")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip)
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


# ------------------------------------------------------------------ #
# Phase 4 fixtures                                                      #
# ------------------------------------------------------------------ #


@pytest.fixture
def valid_api_key():
    """Canonical Phase 4 test API key string."""
    return "eva_test_key_phase4"


@pytest.fixture
def mock_state_valid_key(valid_api_key):
    """Patch server.auth.state_adapter so that valid_api_key appears valid in Redis."""
    from unittest.mock import AsyncMock, patch

    async def fake_get(key: str):
        if key == f"eva:apikey:{valid_api_key}":
            return "1"
        return None

    with patch("server.auth.state_adapter") as mock:
        mock.get = AsyncMock(side_effect=fake_get)
        yield mock


@pytest.fixture
def redis_mock():
    """AsyncMock Redis state adapter with incr/expire support (rate limiter + auth)."""
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=None)
    mock.delete = AsyncMock(return_value=None)
    mock.incr = AsyncMock(return_value=1)
    mock.expire = AsyncMock(return_value=None)
    return mock


@pytest.fixture
def auth_app(valid_api_key):
    """FastAPI test app with ApiKeyMiddleware wired via middleware_factories."""
    from unittest.mock import AsyncMock, patch
    from server.app import create_app
    from server.auth import ApiKeyMiddleware

    app = create_app(middleware_factories=[ApiKeyMiddleware])
    return app
