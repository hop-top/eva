# tests/unit/test_storage.py
import pytest
from datetime import datetime
from core.storage import SqliteStorage
from core.models import Run, Result, Score


@pytest.fixture
def storage(tmp_path):
    return SqliteStorage(db_url=f"sqlite:///{tmp_path}/test.db")


@pytest.fixture
def sample_run():
    return Run(
        run_id="run_001",
        dataset="refunds",
        target="http://localhost:8000",
        started_at=datetime.utcnow(),
        results=[
            Result(
                test_id="t1",
                evaluator="contains",
                score=Score(value=1.0),
                mode="binary",
                duration_ms=42,
                trace_id=None,
            )
        ],
        passed=True,
    )


def test_save_and_retrieve_run(storage, sample_run):
    storage.save_run(sample_run)
    retrieved = storage.get_run("run_001")
    assert retrieved.run_id == "run_001"
    assert retrieved.passed is True


def test_retrieve_results(storage, sample_run):
    storage.save_run(sample_run)
    retrieved = storage.get_run("run_001")
    assert len(retrieved.results) == 1
    assert retrieved.results[0].evaluator == "contains"


def test_missing_run_returns_none(storage):
    assert storage.get_run("nonexistent") is None


def test_list_runs(storage, sample_run):
    storage.save_run(sample_run)
    runs = storage.list_runs()
    assert len(runs) == 1
    assert runs[0].run_id == "run_001"
