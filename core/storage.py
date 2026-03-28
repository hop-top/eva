# core/storage.py
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from sqlmodel import Field, Session, SQLModel, create_engine, select
from core.adapters import StorageAdapter
from core.models import (
    Annotation, Artifact, ContractVersion, DatasetVersion,
    EvaluatorResult, Invocation, Run, Result, Score, ToolCall, UsageRecord,
)


class RunRecord(SQLModel, table=True):
    run_id: str = Field(primary_key=True)
    dataset: str
    target: str
    started_at: datetime
    duration_ms: int
    passed: bool
    results_json: str  # compatibility-only: JSON-serialized list of results


# ---------------------------------------------------------------------------
# Observability table records (P1)
# ---------------------------------------------------------------------------

class ArtifactRecord(SQLModel, table=True):
    __tablename__ = "artifactrecord"

    artifact_id: str = Field(primary_key=True)
    kind: str
    content_type: str
    storage_backend: str
    text_content: Optional[str] = None
    json_content: Optional[str] = None
    blob_path: Optional[str] = None
    sha256: Optional[str] = None
    size_bytes: Optional[int] = None
    redacted: bool = False
    created_at: datetime


class InvocationRecord(SQLModel, table=True):
    __tablename__ = "invocationrecord"

    invocation_id: str = Field(primary_key=True)
    run_id: Optional[str] = Field(default=None, foreign_key="runrecord.run_id")
    source: str
    dataset: Optional[str] = None
    test_id: Optional[str] = None
    target: str
    provider: Optional[str] = None
    model: Optional[str] = None
    model_version: Optional[str] = None
    contract_name: Optional[str] = None
    request_id: Optional[str] = None
    trace_id: Optional[str] = None
    started_at: datetime
    duration_ms: Optional[int] = None
    status: str
    request_artifact_id: Optional[str] = Field(
        default=None, foreign_key="artifactrecord.artifact_id"
    )
    response_artifact_id: Optional[str] = Field(
        default=None, foreign_key="artifactrecord.artifact_id"
    )
    retrieval_artifact_id: Optional[str] = Field(
        default=None, foreign_key="artifactrecord.artifact_id"
    )
    metadata_json: Optional[str] = None


class EvaluatorResultRecord(SQLModel, table=True):
    __tablename__ = "evaluatorresultrecord"

    evaluator_result_id: str = Field(primary_key=True)
    invocation_id: str = Field(foreign_key="invocationrecord.invocation_id")
    evaluator: str
    mode: Optional[str] = None
    min_score: Optional[float] = None
    score_value: Optional[float] = None
    passed: Optional[bool] = None
    reason: Optional[str] = None
    duration_ms: Optional[int] = None
    metadata_json: Optional[str] = None


class ToolCallRecord(SQLModel, table=True):
    __tablename__ = "toolcallrecord"

    tool_call_id: str = Field(primary_key=True)
    invocation_id: str = Field(foreign_key="invocationrecord.invocation_id")
    step_index: int
    tool_name: str
    args_artifact_id: Optional[str] = Field(
        default=None, foreign_key="artifactrecord.artifact_id"
    )
    result_artifact_id: Optional[str] = Field(
        default=None, foreign_key="artifactrecord.artifact_id"
    )
    error_text: Optional[str] = None
    started_at: datetime
    duration_ms: Optional[int] = None
    status: str
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    metadata_json: Optional[str] = None


class UsageRecordRecord(SQLModel, table=True):
    __tablename__ = "usagerecordrecord"

    usage_id: str = Field(primary_key=True)
    invocation_id: str = Field(foreign_key="invocationrecord.invocation_id")
    scope: str
    provider: Optional[str] = None
    model: str
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    estimated_cost_usd: Optional[float] = None
    latency_ms: Optional[int] = None
    raw_usage_json: Optional[str] = None


class AnnotationRecord(SQLModel, table=True):
    __tablename__ = "annotationrecord"

    annotation_id: str = Field(primary_key=True)
    invocation_id: str = Field(foreign_key="invocationrecord.invocation_id")
    reviewer: str
    label: Optional[str] = None
    score: Optional[float] = None
    notes: Optional[str] = None
    corrected_output_artifact_id: Optional[str] = Field(
        default=None, foreign_key="artifactrecord.artifact_id"
    )
    created_at: datetime
    metadata_json: Optional[str] = None


class DatasetVersionRecord(SQLModel, table=True):
    __tablename__ = "datasetversionrecord"

    dataset_version_id: str = Field(primary_key=True)
    dataset: str
    dataset_hash: str
    git_sha: Optional[str] = None
    source_path: str
    created_at: datetime


class ContractVersionRecord(SQLModel, table=True):
    __tablename__ = "contractversionrecord"

    contract_version_id: str = Field(primary_key=True)
    contract_name: str
    contract_hash: str
    git_sha: Optional[str] = None
    artifact_id: Optional[str] = Field(
        default=None, foreign_key="artifactrecord.artifact_id"
    )
    created_at: datetime


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

    # ------------------------------------------------------------------ #
    # Observability methods (P1)                                           #
    # ------------------------------------------------------------------ #

    def save_invocation(
        self,
        invocation: Invocation,
        evaluator_results: list[EvaluatorResult],
        artifacts: list[Artifact],
    ) -> None:
        """Persist invocation, its artifacts, and evaluator results atomically.

        Write order satisfies FK constraints:
          1. ArtifactRecord rows  (referenced by InvocationRecord)
          2. InvocationRecord     (referenced by EvaluatorResultRecord)
          3. EvaluatorResultRecord rows
        """
        with Session(self.engine) as session:
            # 1. Artifacts first (FK dependency for Invocation)
            for artifact in artifacts:
                record = ArtifactRecord(
                    artifact_id=artifact.artifact_id,
                    kind=artifact.kind,
                    content_type=artifact.content_type,
                    storage_backend=artifact.storage_backend,
                    text_content=artifact.text_content,
                    json_content=artifact.json_content,
                    blob_path=artifact.blob_path,
                    sha256=artifact.sha256,
                    size_bytes=artifact.size_bytes,
                    redacted=artifact.redacted,
                    created_at=artifact.created_at,
                )
                session.merge(record)

            # 2. Invocation (FK dependency for EvaluatorResult)
            inv_record = InvocationRecord(
                invocation_id=invocation.invocation_id,
                run_id=invocation.run_id,
                source=invocation.source,
                dataset=invocation.dataset,
                test_id=invocation.test_id,
                target=invocation.target,
                provider=invocation.provider,
                model=invocation.model,
                model_version=invocation.model_version,
                contract_name=invocation.contract_name,
                request_id=invocation.request_id,
                trace_id=invocation.trace_id,
                started_at=invocation.started_at,
                duration_ms=invocation.duration_ms,
                status=invocation.status,
                request_artifact_id=invocation.request_artifact_id,
                response_artifact_id=invocation.response_artifact_id,
                retrieval_artifact_id=invocation.retrieval_artifact_id,
                metadata_json=invocation.metadata_json,
            )
            session.merge(inv_record)

            # 3. EvaluatorResults last (depend on Invocation)
            for er in evaluator_results:
                er_record = EvaluatorResultRecord(
                    evaluator_result_id=er.evaluator_result_id,
                    invocation_id=er.invocation_id,
                    evaluator=er.evaluator,
                    mode=er.mode,
                    min_score=er.min_score,
                    score_value=er.score_value,
                    passed=er.passed,
                    reason=er.reason,
                    duration_ms=er.duration_ms,
                    metadata_json=er.metadata_json,
                )
                session.merge(er_record)

            session.commit()

    def save_tool_calls(
        self,
        invocation_id: str,
        events: list,  # list[ToolCallEvent] — avoid circular import
    ) -> None:
        """Persist ToolCallEvent objects as ToolCallRecord rows.

        Each event is linked to *invocation_id*.  Args/result are stored
        inline as JSON artifacts (inline storage_backend) so no separate
        artifact write path is needed for the common case.
        """
        import uuid as _uuid
        from datetime import timezone

        with Session(self.engine) as session:
            for idx, evt in enumerate(events):
                step = evt.step_index if evt.step_index is not None else idx
                status = "error" if evt.error else "success"

                # Inline artifact for args
                args_artifact_id: Optional[str] = None
                if evt.args:
                    args_artifact_id = str(_uuid.uuid4())
                    now = datetime.now(tz=timezone.utc)
                    session.merge(
                        ArtifactRecord(
                            artifact_id=args_artifact_id,
                            kind="tool_args",
                            content_type="application/json",
                            storage_backend="inline",
                            json_content=json.dumps(evt.args),
                            created_at=now,
                        )
                    )

                # Inline artifact for result (if present)
                result_artifact_id: Optional[str] = None
                if evt.result is not None:
                    result_artifact_id = str(_uuid.uuid4())
                    now = datetime.now(tz=timezone.utc)
                    result_payload = (
                        evt.result
                        if isinstance(evt.result, str)
                        else json.dumps(evt.result)
                    )
                    session.merge(
                        ArtifactRecord(
                            artifact_id=result_artifact_id,
                            kind="tool_result",
                            content_type="application/json",
                            storage_backend="inline",
                            json_content=result_payload,
                            created_at=now,
                        )
                    )

                session.merge(
                    ToolCallRecord(
                        tool_call_id=str(_uuid.uuid4()),
                        invocation_id=invocation_id,
                        step_index=step,
                        tool_name=evt.tool_name,
                        args_artifact_id=args_artifact_id,
                        result_artifact_id=result_artifact_id,
                        error_text=evt.error,
                        started_at=evt.started_at,
                        duration_ms=evt.duration_ms,
                        status=status,
                        trace_id=evt.trace_id,
                        span_id=evt.span_id,
                    )
                )
            session.commit()

    def save_usage_record(self, usage: UsageRecord) -> None:
        """Persist a UsageRecord row (FK: invocation_id must already exist)."""
        record = UsageRecordRecord(
            usage_id=usage.usage_id,
            invocation_id=usage.invocation_id,
            scope=usage.scope,
            provider=usage.provider,
            model=usage.model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            estimated_cost_usd=usage.estimated_cost_usd,
            latency_ms=usage.latency_ms,
            raw_usage_json=usage.raw_usage_json,
        )
        with Session(self.engine) as session:
            session.merge(record)
            session.commit()

    def get_usage_records(self, invocation_id: str) -> list[UsageRecord]:
        """Return all UsageRecord rows for a given invocation_id."""
        with Session(self.engine) as session:
            stmt = select(UsageRecordRecord).where(
                UsageRecordRecord.invocation_id == invocation_id
            )
            records = session.exec(stmt).all()
        return [
            UsageRecord(
                usage_id=r.usage_id,
                invocation_id=r.invocation_id,
                scope=r.scope,
                provider=r.provider,
                model=r.model,
                prompt_tokens=r.prompt_tokens,
                completion_tokens=r.completion_tokens,
                total_tokens=r.total_tokens,
                estimated_cost_usd=r.estimated_cost_usd,
                latency_ms=r.latency_ms,
                raw_usage_json=r.raw_usage_json,
            )
            for r in records
        ]

    def get_invocation(self, invocation_id: str) -> Optional[Invocation]:
        """Return an Invocation by primary key, or None if not found."""
        with Session(self.engine) as session:
            record = session.get(InvocationRecord, invocation_id)
            if not record:
                return None
            return Invocation(
                invocation_id=record.invocation_id,
                run_id=record.run_id,
                source=record.source,  # type: ignore[arg-type]
                dataset=record.dataset,
                test_id=record.test_id,
                target=record.target,
                provider=record.provider,
                model=record.model,
                model_version=record.model_version,
                contract_name=record.contract_name,
                request_id=record.request_id,
                trace_id=record.trace_id,
                started_at=record.started_at,
                duration_ms=record.duration_ms,
                status=record.status,  # type: ignore[arg-type]
                request_artifact_id=record.request_artifact_id,
                response_artifact_id=record.response_artifact_id,
                retrieval_artifact_id=record.retrieval_artifact_id,
                metadata_json=record.metadata_json,
            )

    # ------------------------------------------------------------------ #
    # Annotation methods (T-0141)                                          #
    # ------------------------------------------------------------------ #

    def save_annotation(self, annotation: Annotation) -> None:
        """Persist an Annotation row (FK: invocation_id must already exist)."""
        record = AnnotationRecord(
            annotation_id=annotation.annotation_id,
            invocation_id=annotation.invocation_id,
            reviewer=annotation.reviewer,
            label=annotation.label,
            score=annotation.score,
            notes=annotation.notes,
            corrected_output_artifact_id=annotation.corrected_output_artifact_id,
            created_at=annotation.created_at,
            metadata_json=annotation.metadata_json,
        )
        with Session(self.engine) as session:
            session.merge(record)
            session.commit()

    def list_annotations(self, invocation_id: str) -> list[Annotation]:
        """Return all Annotation rows for a given invocation_id."""
        with Session(self.engine) as session:
            stmt = select(AnnotationRecord).where(
                AnnotationRecord.invocation_id == invocation_id
            )
            records = session.exec(stmt).all()
        return [
            Annotation(
                annotation_id=r.annotation_id,
                invocation_id=r.invocation_id,
                reviewer=r.reviewer,
                label=r.label,
                score=r.score,
                notes=r.notes,
                corrected_output_artifact_id=r.corrected_output_artifact_id,
                created_at=r.created_at,
                metadata_json=r.metadata_json,
            )
            for r in records
        ]

    def delete_annotation(self, annotation_id: str) -> bool:
        """Delete an Annotation by primary key. Returns True if deleted, False if not found."""
        with Session(self.engine) as session:
            record = session.get(AnnotationRecord, annotation_id)
            if record is None:
                return False
            session.delete(record)
            session.commit()
        return True

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
