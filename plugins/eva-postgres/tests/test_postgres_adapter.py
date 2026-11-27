"""
Integration tests — requires Postgres.
Run: pytest --integration plugins/eva-postgres/tests/
Needs psycopg2 (the adapter pins it for bare postgresql:// URLs; SQLAlchemy 2.1 would pick psycopg3).
Docker: docker run -e POSTGRES_PASSWORD=eva -e POSTGRES_DB=eva_test -p 5432:5432 postgres:16-alpine
"""
import os
import uuid
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from core.models import Run, Result, Score

POSTGRES_URL = os.getenv("EVA_POSTGRES_URL", "postgresql://postgres:eva@localhost:5432/eva_test")


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
def test_bare_postgresql_url_end_to_end():
    from eva_postgres.adapter import PostgresStorageAdapter

    bare = make_url(POSTGRES_URL).set(drivername="postgresql")
    assert bare.drivername == "postgresql"
    adapter = PostgresStorageAdapter(url=bare.render_as_string(hide_password=False))
    adapter.setup()
    adapter.save_run(_run("pg_bare_url", datetime(2026, 6, 15, 14, 30, tzinfo=timezone.utc)))

    got = adapter.get_run("pg_bare_url")
    assert got is not None and got.run_id == "pg_bare_url"


@pytest.mark.integration
def test_list_runs():
    from eva_postgres.adapter import PostgresStorageAdapter

    adapter = PostgresStorageAdapter(url=POSTGRES_URL)
    adapter.setup()
    runs = adapter.list_runs(limit=10)
    assert isinstance(runs, list)


def _urls_given_to_create_engine(monkeypatch, url):
    """Build an adapter with create_engine stubbed; return the URL it was given."""
    import eva_postgres.adapter as mod

    seen = []
    monkeypatch.setattr(mod, "create_engine", lambda u, **kw: seen.append(u))
    mod.PostgresStorageAdapter(url=url)
    return make_url(seen[0])


def test_bare_postgresql_url_uses_psycopg2_engine():
    from eva_postgres.adapter import PostgresStorageAdapter

    adapter = PostgresStorageAdapter(url="postgresql://u:p@localhost/db")
    assert adapter.engine.dialect.driver == "psycopg2"


@pytest.mark.parametrize(
    "driver", ["postgresql+psycopg2", "postgresql+psycopg", "postgresql+asyncpg"]
)
def test_explicit_driver_is_left_as_given(monkeypatch, driver):
    given = f"{driver}://u:p@localhost/db"
    assert _urls_given_to_create_engine(monkeypatch, given).drivername == driver


def test_bare_url_keeps_credentials_and_query(monkeypatch):
    given = make_url("postgresql://us%40r:p%3A%2Fw%40d%25@db.example:5433/eva")
    given = given.update_query_dict(
        {"options": "-c search_path=s -c timezone=UTC", "sslmode": "require"}
    )
    out = _urls_given_to_create_engine(
        monkeypatch, given.render_as_string(hide_password=False)
    )

    assert out.drivername == "postgresql+psycopg2"
    assert out.username == "us@r"
    assert out.password == "p:/w@d%"
    assert (out.host, out.port, out.database) == ("db.example", 5433, "eva")
    assert dict(out.query) == dict(given.query)


@pytest.fixture
def fresh_adapter():
    """Adapter on a table created from scratch, in a private schema.

    The session time zone is pinned to UTC so results do not depend on the
    server default. The schema is dropped afterwards.
    """
    from eva_postgres.adapter import PostgresStorageAdapter

    schema = f"eva_tz_{uuid.uuid4().hex[:12]}"
    # Plain SQLAlchemy engine (not the adapter): name the driver explicitly.
    admin = create_engine(make_url(POSTGRES_URL).set(drivername="postgresql+psycopg2"))
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
