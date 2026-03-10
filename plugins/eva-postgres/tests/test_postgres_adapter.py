"""
Integration tests — requires Postgres.
Run: pytest --integration plugins/eva-postgres/tests/
Docker: docker run -e POSTGRES_PASSWORD=eva -e POSTGRES_DB=eva_test -p 5432:5432 postgres:16-alpine
"""
import os
import pytest
from datetime import datetime
from core.models import Run, Result, Score

POSTGRES_URL = os.getenv("EVA_POSTGRES_URL", "postgresql://postgres:eva@localhost:5432/eva_test")


def pytest_addoption(parser):
    parser.addoption("--integration", action="store_true", default=False)


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--integration"):
        skip = pytest.mark.skip(reason="Pass --integration to run Postgres tests")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip)


@pytest.mark.integration
def test_save_and_retrieve_run():
    from eva_postgres.adapter import PostgresStorageAdapter

    adapter = PostgresStorageAdapter(url=POSTGRES_URL)
    adapter.setup()

    run = Run(
        run_id="pg_test_001",
        dataset="test_dataset",
        target="http://agent:8000",
        started_at=datetime.utcnow(),
        results=[
            Result(
                test_id="t1",
                evaluator="contains",
                score=Score(value=1.0),
                mode="binary",
                duration_ms=5,
                trace_id=None,
            )
        ],
        passed=True,
    )
    adapter.save_run(run)

    retrieved = adapter.get_run("pg_test_001")
    assert retrieved is not None
    assert retrieved.run_id == "pg_test_001"
    assert retrieved.passed is True
    assert len(retrieved.results) == 1


@pytest.mark.integration
def test_list_runs():
    from eva_postgres.adapter import PostgresStorageAdapter

    adapter = PostgresStorageAdapter(url=POSTGRES_URL)
    adapter.setup()
    runs = adapter.list_runs(limit=10)
    assert isinstance(runs, list)
