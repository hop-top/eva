# conftest.py (repo root)
# --integration is registered here so it is available for every test path,
# including plugin test dirs outside tests/.
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
