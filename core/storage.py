# core/storage.py
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from sqlmodel import Field, Session, SQLModel, create_engine, select
from core.adapters import StorageAdapter
from core.models import Run, Result, Score


class RunRecord(SQLModel, table=True):
    run_id: str = Field(primary_key=True)
    dataset: str
    target: str
    started_at: datetime
    duration_ms: int
    passed: bool
    results_json: str  # JSON-serialized list of results


class SqliteStorage(StorageAdapter):
    def __init__(self, db_url: str = "sqlite:///.eva/state.db"):
        if db_url.startswith("sqlite:///"):
            path = Path(db_url.replace("sqlite:///", ""))
            if not path.name == ":memory:":
                path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(db_url)
        SQLModel.metadata.create_all(self.engine)

    # ------------------------------------------------------------------ #
    # StorageAdapter async interface                                        #
    # ------------------------------------------------------------------ #

    async def save_result(self, result: Any) -> None:
        """Persist a Run (or any model with .model_dump()) via save_run."""
        self.save_run(result)

    async def load_results(self, run_id: str) -> list[Any]:
        """Load all Result objects for a given run_id."""
        run = self.get_run(run_id)
        return run.results if run else []

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

    def get_run(self, run_id: str) -> Optional[Run]:
        with Session(self.engine) as session:
            record = session.get(RunRecord, run_id)
            if not record:
                return None
            return self._record_to_run(record)

    def list_runs(self) -> list[Run]:
        with Session(self.engine) as session:
            records = session.exec(select(RunRecord)).all()
            return [self._record_to_run(r) for r in records]

    async def get_runs(
        self, dataset: str, target: str, limit: int = 10
    ) -> list[Run]:
        """Return the most recent `limit` runs for a (dataset, target) pair.

        Results are returned oldest-first so drift detection sees natural order.
        """
        with Session(self.engine) as session:
            stmt = (
                select(RunRecord)
                .where(RunRecord.dataset == dataset)
                .where(RunRecord.target == target)
                .order_by(RunRecord.started_at.desc())  # type: ignore[attr-defined]
                .limit(limit)
            )
            records = session.exec(stmt).all()
        # Reverse so caller gets oldest-first
        return [self._record_to_run(r) for r in reversed(records)]

    def _record_to_run(self, record: RunRecord) -> Run:
        results = [Result.model_validate(r) for r in json.loads(record.results_json)]
        return Run(
            run_id=record.run_id,
            dataset=record.dataset,
            target=record.target,
            results=results,
            started_at=record.started_at,
            duration_ms=record.duration_ms,
            passed=record.passed,
        )
