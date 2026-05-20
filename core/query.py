# core/query.py
"""Read-only query/filter layer over SqliteStorage.

Powers CLI commands.  No side effects — all functions are pure reads.
"""
from __future__ import annotations

from typing import Optional

from sqlmodel import Session, select

from core.models import (
    Annotation,
    Artifact,
    EvaluatorResult,
    Invocation,
    Run,
    ToolCall,
    UsageRecord,
)
from core.storage import (
    AnnotationRecord,
    ArtifactRecord,
    EvaluatorResultRecord,
    InvocationRecord,
    RunRecord,
    SqliteStorage,
    ToolCallRecord,
    UsageRecordRecord,
)


# ---------------------------------------------------------------------------
# Internal converters
# ---------------------------------------------------------------------------

def _inv_record_to_model(r: InvocationRecord) -> Invocation:
    return Invocation(
        invocation_id=r.invocation_id,
        run_id=r.run_id,
        source=r.source,  # type: ignore[arg-type]
        dataset=r.dataset,
        test_id=r.test_id,
        target=r.target,
        provider=r.provider,
        model=r.model,
        model_version=r.model_version,
        contract_name=r.contract_name,
        request_id=r.request_id,
        trace_id=r.trace_id,
        started_at=r.started_at,
        duration_ms=r.duration_ms,
        status=r.status,  # type: ignore[arg-type]
        request_artifact_id=r.request_artifact_id,
        response_artifact_id=r.response_artifact_id,
        retrieval_artifact_id=r.retrieval_artifact_id,
        metadata_json=r.metadata_json,
    )


def _er_record_to_model(r: EvaluatorResultRecord) -> EvaluatorResult:
    return EvaluatorResult(
        evaluator_result_id=r.evaluator_result_id,
        invocation_id=r.invocation_id,
        evaluator=r.evaluator,
        mode=r.mode,
        min_score=r.min_score,
        score_value=r.score_value,
        passed=r.passed,
        reason=r.reason,
        duration_ms=r.duration_ms,
        metadata_json=r.metadata_json,
    )


def _tc_record_to_model(r: ToolCallRecord) -> ToolCall:
    return ToolCall(
        tool_call_id=r.tool_call_id,
        invocation_id=r.invocation_id,
        step_index=r.step_index,
        tool_name=r.tool_name,
        args_artifact_id=r.args_artifact_id,
        result_artifact_id=r.result_artifact_id,
        error_text=r.error_text,
        started_at=r.started_at,
        duration_ms=r.duration_ms,
        status=r.status,
        trace_id=r.trace_id,
        span_id=r.span_id,
        metadata_json=r.metadata_json,
    )


def _ur_record_to_model(r: UsageRecordRecord) -> UsageRecord:
    return UsageRecord(
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


def _ann_record_to_model(r: AnnotationRecord) -> Annotation:
    return Annotation(
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


def _artifact_record_to_model(r: ArtifactRecord) -> Artifact:
    return Artifact(
        artifact_id=r.artifact_id,
        kind=r.kind,  # type: ignore[arg-type]
        content_type=r.content_type,
        storage_backend=r.storage_backend,  # type: ignore[arg-type]
        text_content=r.text_content,
        json_content=r.json_content,
        blob_path=r.blob_path,
        sha256=r.sha256,
        size_bytes=r.size_bytes,
        redacted=r.redacted,
        created_at=r.created_at,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_runs(
    storage: SqliteStorage,
    *,
    dataset: Optional[str] = None,
    target: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> list[Run]:
    """Return runs, optionally filtered by dataset / target / passed status.

    *status* accepts "pass" or "fail" (maps to RunRecord.passed bool).
    """
    with Session(storage.engine) as session:
        stmt = select(RunRecord).order_by(
            RunRecord.started_at.desc()  # type: ignore[attr-defined]
        )
        if dataset is not None:
            stmt = stmt.where(RunRecord.dataset == dataset)
        if target is not None:
            stmt = stmt.where(RunRecord.target == target)
        if status is not None:
            passed = status.lower() == "pass"
            stmt = stmt.where(RunRecord.passed == passed)
        stmt = stmt.limit(limit)
        records = session.exec(stmt).all()
    return [storage._record_to_run(r) for r in records]


def list_invocations(
    storage: SqliteStorage,
    *,
    run_id: Optional[str] = None,
    dataset: Optional[str] = None,
    model: Optional[str] = None,
    contract_name: Optional[str] = None,
    status: Optional[str] = None,
    evaluator: Optional[str] = None,
    min_duration_ms: Optional[int] = None,
    max_duration_ms: Optional[int] = None,
    limit: int = 50,
) -> list[Invocation]:
    """Return invocations matching all supplied filters."""
    with Session(storage.engine) as session:
        stmt = select(InvocationRecord).order_by(
            InvocationRecord.started_at.desc()  # type: ignore[attr-defined]
        )
        if run_id is not None:
            stmt = stmt.where(InvocationRecord.run_id == run_id)
        if dataset is not None:
            stmt = stmt.where(InvocationRecord.dataset == dataset)
        if model is not None:
            stmt = stmt.where(InvocationRecord.model == model)
        if contract_name is not None:
            stmt = stmt.where(InvocationRecord.contract_name == contract_name)
        if status is not None:
            stmt = stmt.where(InvocationRecord.status == status)
        if min_duration_ms is not None:
            stmt = stmt.where(InvocationRecord.duration_ms >= min_duration_ms)
        if max_duration_ms is not None:
            stmt = stmt.where(InvocationRecord.duration_ms <= max_duration_ms)

        if evaluator is not None:
            # Filter via a sub-select on EvaluatorResultRecord
            sub = select(EvaluatorResultRecord.invocation_id).where(
                EvaluatorResultRecord.evaluator == evaluator
            )
            stmt = stmt.where(InvocationRecord.invocation_id.in_(sub))  # type: ignore[attr-defined]

        stmt = stmt.limit(limit)
        records = session.exec(stmt).all()
    return [_inv_record_to_model(r) for r in records]


def get_invocation_detail(
    storage: SqliteStorage,
    invocation_id: str,
) -> dict:
    """Return a dict with invocation plus all related rows.

    Keys: invocation, evaluator_results, tool_calls, usage_records, artifacts
    """
    with Session(storage.engine) as session:
        inv_rec = session.get(InvocationRecord, invocation_id)
        if inv_rec is None:
            return {}

        invocation = _inv_record_to_model(inv_rec)

        er_records = session.exec(
            select(EvaluatorResultRecord).where(
                EvaluatorResultRecord.invocation_id == invocation_id
            )
        ).all()
        evaluator_results = [_er_record_to_model(r) for r in er_records]

        tc_records = session.exec(
            select(ToolCallRecord)
            .where(ToolCallRecord.invocation_id == invocation_id)
            .order_by(ToolCallRecord.step_index)  # type: ignore[attr-defined]
        ).all()
        tool_calls = [_tc_record_to_model(r) for r in tc_records]

        ur_records = session.exec(
            select(UsageRecordRecord).where(
                UsageRecordRecord.invocation_id == invocation_id
            )
        ).all()
        usage_records = [_ur_record_to_model(r) for r in ur_records]

        # Collect all artifact IDs referenced by this invocation + its tool calls
        artifact_ids: set[str] = set()
        for aid in (
            inv_rec.request_artifact_id,
            inv_rec.response_artifact_id,
            inv_rec.retrieval_artifact_id,
        ):
            if aid:
                artifact_ids.add(aid)
        for tc in tc_records:
            if tc.args_artifact_id:
                artifact_ids.add(tc.args_artifact_id)
            if tc.result_artifact_id:
                artifact_ids.add(tc.result_artifact_id)

        artifacts: list[Artifact] = []
        if artifact_ids:
            art_records = session.exec(
                select(ArtifactRecord).where(
                    ArtifactRecord.artifact_id.in_(artifact_ids)  # type: ignore[attr-defined]
                )
            ).all()
            artifacts = [_artifact_record_to_model(r) for r in art_records]

    return {
        "invocation": invocation,
        "evaluator_results": evaluator_results,
        "tool_calls": tool_calls,
        "usage_records": usage_records,
        "artifacts": artifacts,
    }


def compare_runs(
    storage: SqliteStorage,
    left_run_id: str,
    right_run_id: str,
) -> dict:
    """Side-by-side comparison of two runs.

    Returns:
        left / right Run objects, plus per-evaluator diffs for:
          - pass_rate, avg_score, avg_cost_usd, models used
        And summary-level diffs: total_cost_usd, pass_rate, model sets.
    """
    with Session(storage.engine) as session:
        left_run_rec = session.get(RunRecord, left_run_id)
        right_run_rec = session.get(RunRecord, right_run_id)

        if left_run_rec is None or right_run_rec is None:
            missing = []
            if left_run_rec is None:
                missing.append(left_run_id)
            if right_run_rec is None:
                missing.append(right_run_id)
            return {"error": f"Run(s) not found: {missing}"}

        left_run = storage._record_to_run(left_run_rec)
        right_run = storage._record_to_run(right_run_rec)

        def _stats_for_run(run_id: str) -> dict:
            inv_ids: list[str] = [
                r.invocation_id
                for r in session.exec(
                    select(InvocationRecord).where(
                        InvocationRecord.run_id == run_id
                    )
                ).all()
            ]

            total_cost: float = 0.0
            model_counts: dict[str, int] = {}
            if inv_ids:
                ur_rows = session.exec(
                    select(UsageRecordRecord).where(
                        UsageRecordRecord.invocation_id.in_(inv_ids)  # type: ignore[attr-defined]
                    )
                ).all()
                for ur in ur_rows:
                    total_cost += ur.estimated_cost_usd or 0.0
                    model_counts[ur.model] = model_counts.get(ur.model, 0) + 1

            evaluator_stats: dict[str, dict] = {}
            if inv_ids:
                er_rows = session.exec(
                    select(EvaluatorResultRecord).where(
                        EvaluatorResultRecord.invocation_id.in_(inv_ids)  # type: ignore[attr-defined]
                    )
                ).all()
                for er in er_rows:
                    ev = er.evaluator
                    if ev not in evaluator_stats:
                        evaluator_stats[ev] = {"passed": 0, "total": 0, "scores": []}
                    evaluator_stats[ev]["total"] += 1
                    if er.passed:
                        evaluator_stats[ev]["passed"] += 1
                    if er.score_value is not None:
                        evaluator_stats[ev]["scores"].append(er.score_value)

            per_evaluator: dict[str, dict] = {}
            for ev, s in evaluator_stats.items():
                scores = s["scores"]
                per_evaluator[ev] = {
                    "pass_rate": s["passed"] / s["total"] if s["total"] else None,
                    "avg_score": sum(scores) / len(scores) if scores else None,
                    "total": s["total"],
                }

            return {
                "total_cost_usd": total_cost,
                "models": model_counts,
                "per_evaluator": per_evaluator,
                "invocation_count": len(inv_ids),
            }

        left_stats = _stats_for_run(left_run_id)
        right_stats = _stats_for_run(right_run_id)

    all_evaluators = set(left_stats["per_evaluator"]) | set(right_stats["per_evaluator"])
    evaluator_diffs: dict[str, dict] = {}
    for ev in all_evaluators:
        lev = left_stats["per_evaluator"].get(ev, {})
        rev = right_stats["per_evaluator"].get(ev, {})
        l_pr = lev.get("pass_rate")
        r_pr = rev.get("pass_rate")
        l_sc = lev.get("avg_score")
        r_sc = rev.get("avg_score")
        evaluator_diffs[ev] = {
            "left_pass_rate": l_pr,
            "right_pass_rate": r_pr,
            "pass_rate_diff": (r_pr - l_pr) if (l_pr is not None and r_pr is not None) else None,
            "left_avg_score": l_sc,
            "right_avg_score": r_sc,
            "score_diff": (r_sc - l_sc) if (l_sc is not None and r_sc is not None) else None,
        }

    return {
        "left": left_run,
        "right": right_run,
        "left_stats": left_stats,
        "right_stats": right_stats,
        "cost_diff_usd": right_stats["total_cost_usd"] - left_stats["total_cost_usd"],
        "evaluator_diffs": evaluator_diffs,
    }


def list_failures(
    storage: SqliteStorage,
    *,
    evaluator: Optional[str] = None,
    model: Optional[str] = None,
    contract_name: Optional[str] = None,
    dataset: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Return failed EvaluatorResult rows with their parent Invocation context.

    Each dict: {invocation: Invocation, evaluator_result: EvaluatorResult}.
    """
    with Session(storage.engine) as session:
        stmt = (
            select(EvaluatorResultRecord)
            .where(EvaluatorResultRecord.passed == False)  # noqa: E712
            .order_by(
                EvaluatorResultRecord.evaluator_result_id.desc()  # type: ignore[attr-defined]
            )
        )
        if evaluator is not None:
            stmt = stmt.where(EvaluatorResultRecord.evaluator == evaluator)

        needs_inv_filter = model or contract_name or dataset
        if needs_inv_filter:
            inv_sub = select(InvocationRecord.invocation_id)  # type: ignore[attr-defined]
            if model is not None:
                inv_sub = inv_sub.where(InvocationRecord.model == model)
            if contract_name is not None:
                inv_sub = inv_sub.where(InvocationRecord.contract_name == contract_name)
            if dataset is not None:
                inv_sub = inv_sub.where(InvocationRecord.dataset == dataset)
            stmt = stmt.where(
                EvaluatorResultRecord.invocation_id.in_(inv_sub)  # type: ignore[attr-defined]
            )

        stmt = stmt.limit(limit)
        er_records = session.exec(stmt).all()

        inv_ids = list({r.invocation_id for r in er_records})
        inv_map: dict[str, Invocation] = {}
        if inv_ids:
            inv_rows = session.exec(
                select(InvocationRecord).where(
                    InvocationRecord.invocation_id.in_(inv_ids)  # type: ignore[attr-defined]
                )
            ).all()
            inv_map = {r.invocation_id: _inv_record_to_model(r) for r in inv_rows}

    return [
        {
            "invocation": inv_map.get(r.invocation_id),
            "evaluator_result": _er_record_to_model(r),
        }
        for r in er_records
    ]


def usage_report(
    storage: SqliteStorage,
    *,
    dataset: Optional[str] = None,
    target: Optional[str] = None,
) -> dict:
    """Aggregate token and cost totals, with per-model breakdown.

    Filters on InvocationRecord.dataset / target when supplied.
    Returns:
        totals: {prompt_tokens, completion_tokens, total_tokens, estimated_cost_usd}
        by_model: {model -> same shape}
        invocation_count: int
    """
    with Session(storage.engine) as session:
        if dataset is not None or target is not None:
            inv_stmt = select(InvocationRecord)
            if dataset is not None:
                inv_stmt = inv_stmt.where(InvocationRecord.dataset == dataset)
            if target is not None:
                inv_stmt = inv_stmt.where(InvocationRecord.target == target)
            inv_rows = session.exec(inv_stmt).all()
            inv_ids = [r.invocation_id for r in inv_rows]
            inv_count = len(inv_ids)

            if inv_ids:
                ur_rows = session.exec(
                    select(UsageRecordRecord).where(
                        UsageRecordRecord.invocation_id.in_(inv_ids)  # type: ignore[attr-defined]
                    )
                ).all()
            else:
                ur_rows = []
        else:
            ur_rows = session.exec(select(UsageRecordRecord)).all()
            inv_count = len(session.exec(select(InvocationRecord)).all())

    totals: dict[str, float] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "estimated_cost_usd": 0.0,
    }
    by_model: dict[str, dict[str, float]] = {}

    for ur in ur_rows:
        totals["prompt_tokens"] += ur.prompt_tokens or 0
        totals["completion_tokens"] += ur.completion_tokens or 0
        totals["total_tokens"] += ur.total_tokens or 0
        totals["estimated_cost_usd"] += ur.estimated_cost_usd or 0.0

        m = ur.model
        if m not in by_model:
            by_model[m] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "estimated_cost_usd": 0.0,
            }
        by_model[m]["prompt_tokens"] += ur.prompt_tokens or 0
        by_model[m]["completion_tokens"] += ur.completion_tokens or 0
        by_model[m]["total_tokens"] += ur.total_tokens or 0
        by_model[m]["estimated_cost_usd"] += ur.estimated_cost_usd or 0.0

    return {
        "totals": totals,
        "by_model": by_model,
        "invocation_count": inv_count,
    }


def review_queue(
    storage: SqliteStorage,
    *,
    failed_only: bool = False,
) -> list[dict]:
    """Return invocations pending human review.

    An invocation qualifies when it has no annotation yet, or when any of its
    evaluator results failed.  When *failed_only* is True only invocations
    with at least one failing evaluator result are returned.

    Each dict contains:
      invocation       – Invocation model
      evaluator_results – list[EvaluatorResult]
      annotations      – list[Annotation] (may be empty)
      needs_review     – bool (True when no annotation yet)
      has_failure      – bool (True when any evaluator result failed)
    """
    with Session(storage.engine) as session:
        # Find invocation_ids that have at least one failing evaluator result
        failed_inv_ids: set[str] = {
            r.invocation_id
            for r in session.exec(
                select(EvaluatorResultRecord).where(
                    EvaluatorResultRecord.passed == False  # noqa: E712
                )
            ).all()
        }

        # Find invocation_ids that already have an annotation
        annotated_inv_ids: set[str] = {
            r.invocation_id
            for r in session.exec(select(AnnotationRecord)).all()
        }

        if failed_only:
            candidate_ids = list(failed_inv_ids)
        else:
            # Any invocation that is either unannotated or has a failure
            all_inv_ids: set[str] = {
                r.invocation_id for r in session.exec(select(InvocationRecord)).all()
            }
            unannotated = all_inv_ids - annotated_inv_ids
            candidate_ids = list(unannotated | failed_inv_ids)

        if not candidate_ids:
            return []

        inv_rows = session.exec(
            select(InvocationRecord).where(
                InvocationRecord.invocation_id.in_(candidate_ids)  # type: ignore[attr-defined]
            )
        ).all()

        results: list[dict] = []
        for inv_rec in inv_rows:
            inv = _inv_record_to_model(inv_rec)
            iid = inv.invocation_id

            er_rows = session.exec(
                select(EvaluatorResultRecord).where(
                    EvaluatorResultRecord.invocation_id == iid
                )
            ).all()
            evaluator_results = [_er_record_to_model(r) for r in er_rows]

            ann_rows = session.exec(
                select(AnnotationRecord).where(
                    AnnotationRecord.invocation_id == iid
                )
            ).all()
            annotations = [_ann_record_to_model(r) for r in ann_rows]

            has_failure = iid in failed_inv_ids
            needs_review = iid not in annotated_inv_ids

            results.append({
                "invocation": inv,
                "evaluator_results": evaluator_results,
                "annotations": annotations,
                "needs_review": needs_review,
                "has_failure": has_failure,
            })

    return results
