from __future__ import annotations
import json
from datetime import datetime
from sqlmodel import SQLModel, Field, Session, create_engine, select
from sqlalchemy import Column, Text
from core.models import Run, Result


class RunRecord(SQLModel, table=True):
    __tablename__ = "eva_runs"

    run_id: str = Field(primary_key=True)
    dataset: str
    target: str
    started_at: datetime
    duration_ms: int = 0
    passed: bool = False
    results_json: str = Field(sa_column=Column(Text))


class PostgresStorageAdapter:
    """
    PostgreSQL storage adapter for Eva.

    Usage:
        adapter = PostgresStorageAdapter(url="postgresql://user:pass@host/dbname")
        adapter.setup()  # creates tables
        adapter.save_run(run)
        run = adapter.get_run("run_id")
    """

    def __init__(self, url: str) -> None:
        self.engine = create_engine(url)

    def setup(self) -> None:
        SQLModel.metadata.create_all(self.engine)

    def save_run(self, run: Run) -> None:
        record = RunRecord(
            run_id=run.run_id,
            dataset=run.dataset,
            target=run.target,
            started_at=run.started_at,
            duration_ms=run.duration_ms,
            passed=run.passed,
            results_json=json.dumps([r.model_dump() for r in run.results]),
        )
        with Session(self.engine) as session:
            session.merge(record)
            session.commit()

    def get_run(self, run_id: str) -> Run | None:
        with Session(self.engine) as session:
            record = session.get(RunRecord, run_id)
            if record is None:
                return None
            return self._to_run(record)

    def list_runs(self, limit: int = 100) -> list[Run]:
        with Session(self.engine) as session:
            records = session.exec(select(RunRecord).limit(limit)).all()
            return [self._to_run(r) for r in records]

    def _to_run(self, record: RunRecord) -> Run:
        results_data = json.loads(record.results_json)
        results = [Result.model_validate(r) for r in results_data]
        return Run(
            run_id=record.run_id,
            dataset=record.dataset,
            target=record.target,
            started_at=record.started_at,
            duration_ms=record.duration_ms,
            passed=record.passed,
            results=results,
        )
