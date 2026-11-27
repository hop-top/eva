"""
Integration tests — requires Postgres.
Run: pytest --integration plugins/eva-postgres/tests/
Needs psycopg2 (the URL pins the driver; SQLAlchemy 2.1 defaults bare postgresql:// to psycopg3).
Docker: docker run -e POSTGRES_PASSWORD=eva -e POSTGRES_DB=eva_test -p 5432:5432 postgres:16-alpine
"""
import os
import uuid
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from core.models import Run, Result, Score

POSTGRES_URL = os.getenv("EVA_POSTGRES_URL", "postgresql+psycopg2://postgres:eva@localhost:5432/eva_test")


@pytest.mark.integration
def test_save_and_retrieve_run():
    from eva_postgres.adapter import PostgresStorageAdapter

    adapter = PostgresStorageAdapter(url=POSTGRES_URL)
    adapter.setup()

    run = Run(
        run_id="pg_test_001",
        dataset="test_dataset",
        target="http://agent:8000",
        started_at=datetime.now(timezone.utc),
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


@pytest.fixture
def fresh_adapter():
    """Adapter on a table created from scratch, in a private schema.

    The session time zone is pinned to UTC so results do not depend on the
    server default. The schema is dropped afterwards.
    """
    from eva_postgres.adapter import PostgresStorageAdapter

    schema = f"eva_tz_{uuid.uuid4().hex[:12]}"
    admin = create_engine(POSTGRES_URL)
    with admin.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    url = make_url(POSTGRES_URL).update_query_dict(
        {"options": f"-c search_path={schema} -c timezone=UTC"}
    )
    adapter = PostgresStorageAdapter(url=url.render_as_string(hide_password=False))
    try:
        adapter.setup()
        yield adapter
    finally:
        adapter.engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


def _utc(value: datetime) -> datetime:
    """Normalize to an aware UTC instant (naive values are read as UTC)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _run(run_id: str, started_at: datetime, duration_ms: int = 1) -> Run:
    return Run(
        run_id=run_id,
        dataset="d",
        target="t",
        started_at=started_at,
        duration_ms=duration_ms,
        passed=True,
        results=[],
    )


@pytest.mark.integration
def test_started_at_round_trips_same_instant(fresh_adapter):
    started = datetime(2026, 6, 15, 14, 30, 0, 123456, tzinfo=timezone.utc)
    fresh_adapter.save_run(_run("tz_utc", started))

    assert _utc(fresh_adapter.get_run("tz_utc").started_at) == started
    listed = {r.run_id: r for r in fresh_adapter.list_runs()}
    assert _utc(listed["tz_utc"].started_at) == started


@pytest.mark.integration
def test_non_utc_offset_round_trips_same_instant(fresh_adapter):
    started = datetime(
        2026, 6, 15, 10, 30, 0, 123456, tzinfo=timezone(timedelta(hours=-4))
    )
    fresh_adapter.save_run(_run("tz_offset", started))

    assert _utc(fresh_adapter.get_run("tz_offset").started_at) == started


@pytest.mark.integration
def test_save_run_upserts_existing_row(fresh_adapter):
    started = datetime(2026, 6, 15, 14, 30, tzinfo=timezone.utc)
    fresh_adapter.save_run(_run("tz_upsert", started, duration_ms=1))
    fresh_adapter.save_run(_run("tz_upsert", started, duration_ms=99))

    rows = [r for r in fresh_adapter.list_runs() if r.run_id == "tz_upsert"]
    assert len(rows) == 1
    assert rows[0].duration_ms == 99
    assert _utc(rows[0].started_at) == started
