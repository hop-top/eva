# tests/unit/test_storage_adapter.py
"""Tests for StorageAdapter interface on SqliteStorage."""
import pytest
from datetime import datetime
from core.storage import SqliteStorage
from core.models import Run, Result, Score


@pytest.fixture
def storage():
    return SqliteStorage(db_url="sqlite:///:memory:")


@pytest.fixture
def sample_run():
    return Run(
        run_id="run_async_001",
        dataset="refunds",
        target="http://localhost:8000",
        started_at=datetime.utcnow(),
        results=[
            Result(
                test_id="t1",
                evaluator="contains",
                score=Score(value=1.0),
                mode="binary",
                duration_ms=10,
            )
        ],
        passed=True,
    )


@pytest.mark.asyncio
async def test_save_result_and_load_results(storage, sample_run):
    await storage.save_result(sample_run)
    results = await storage.load_results("run_async_001")
    assert len(results) == 1
    assert results[0].test_id == "t1"


@pytest.mark.asyncio
async def test_load_results_missing_run(storage):
    results = await storage.load_results("nonexistent")
    assert results == []


def test_sqlite_storage_is_storage_adapter(storage):
    from core.adapters import StorageAdapter
    assert isinstance(storage, StorageAdapter)
