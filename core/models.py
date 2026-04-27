# core/models.py
from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, model_validator


class Score(BaseModel):
    value: float
    reason: str | None = None
    metadata: dict = {}


class EvaluatorRef(BaseModel):
    # Per-evaluator config (substring, pattern, schema, …) flows through as
    # extras so gateway + CLI share one source of truth (T-0260).
    model_config = ConfigDict(extra="allow")

    name: str
    mode: Literal["binary", "threshold", "warn"] = "binary"
    min_score: float = 1.0


class RetryPolicy(BaseModel):
    max_retries: int = 2
    hint: str | None = None
    backoff_ms: int = 0


class Contract(BaseModel):
    name: str
    provider: str
    consumer: str | None = None
    request_schema: dict = {}
    evaluators: list[EvaluatorRef] = []
    retry_policy: RetryPolicy = RetryPolicy()


class Result(BaseModel):
    test_id: str
    evaluator: str
    score: Score
    mode: Literal["binary", "threshold", "warn"]
    min_score: float = 1.0
    passed: bool = False
    duration_ms: int
    trace_id: str | None = None

    @model_validator(mode="after")
    def compute_passed(self) -> "Result":
        # NOTE: keep in sync with cli/run_contract.py::_passed
        # (standalone CLI duplicates this logic to avoid the
        # eva[server] extras dep). If you change either, update both.
        if self.mode == "binary":
            self.passed = self.score.value == 1.0
        elif self.mode == "threshold":
            self.passed = self.score.value >= self.min_score
        elif self.mode == "warn":
            self.passed = True
        return self


class Run(BaseModel):
    run_id: str
    dataset: str
    target: str
    results: list[Result] = []
    started_at: datetime
    duration_ms: int = 0
    passed: bool = False


# ---------------------------------------------------------------------------
# Observability models (P1)
# ---------------------------------------------------------------------------

ArtifactKind = Literal[
    "request", "response", "retrieval", "tool_args", "tool_result", "annotation_attachment"
]
StorageBackend = Literal["inline", "sqlite_blob", "file"]
InvocationSource = Literal["offline_run", "gateway_proxy", "contract_invoke"]
InvocationStatus = Literal["pass", "fail", "upstream_error", "request_invalid"]


class Artifact(BaseModel):
    artifact_id: str  # UUID as str
    kind: ArtifactKind
    content_type: str
    storage_backend: StorageBackend
    text_content: Optional[str] = None
    json_content: Optional[str] = None
    blob_path: Optional[str] = None
    sha256: Optional[str] = None
    size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    redacted: bool = False
    created_at: datetime


class Invocation(BaseModel):
    invocation_id: str  # UUID as str
    run_id: Optional[str] = None  # FK to Run
    source: InvocationSource
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
    status: InvocationStatus
    request_artifact_id: Optional[str] = None   # FK to Artifact
    response_artifact_id: Optional[str] = None  # FK to Artifact
    retrieval_artifact_id: Optional[str] = None # FK to Artifact
    metadata_json: Optional[str] = None


class EvaluatorResult(BaseModel):
    evaluator_result_id: str  # UUID as str
    invocation_id: str        # FK to Invocation
    evaluator: str
    mode: Optional[str] = None
    min_score: Optional[float] = None
    score_value: Optional[float] = None
    passed: Optional[bool] = None
    reason: Optional[str] = None
    duration_ms: Optional[int] = None
    metadata_json: Optional[str] = None


class ToolCall(BaseModel):
    tool_call_id: str          # UUID as str
    invocation_id: str         # FK to Invocation
    step_index: int
    tool_name: str
    args_artifact_id: Optional[str] = None    # FK to Artifact
    result_artifact_id: Optional[str] = None  # FK to Artifact
    error_text: Optional[str] = None
    started_at: datetime
    duration_ms: Optional[int] = None
    status: str  # "success" | "error"
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    metadata_json: Optional[str] = None


class UsageRecord(BaseModel):
    usage_id: str              # UUID as str
    invocation_id: str         # FK to Invocation
    scope: str                 # "agent" | "evaluator_judge" | "tool"
    provider: Optional[str] = None
    model: str
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    estimated_cost_usd: Optional[float] = None
    latency_ms: Optional[int] = None
    raw_usage_json: Optional[str] = None


class Annotation(BaseModel):
    annotation_id: str                          # UUID as str
    invocation_id: str                          # FK to Invocation
    reviewer: str
    label: Optional[str] = None
    score: Optional[float] = None
    notes: Optional[str] = None
    corrected_output_artifact_id: Optional[str] = None  # FK to Artifact
    created_at: datetime
    metadata_json: Optional[str] = None


class DatasetVersion(BaseModel):
    dataset_version_id: str    # UUID as str
    dataset: str
    dataset_hash: str
    git_sha: Optional[str] = None
    source_path: str
    created_at: datetime


class ContractVersion(BaseModel):
    contract_version_id: str   # UUID as str
    contract_name: str
    contract_hash: str
    git_sha: Optional[str] = None
    artifact_id: Optional[str] = None  # FK to Artifact
    created_at: datetime


# ---------------------------------------------------------------------------
# Multi-turn conversation models
# ---------------------------------------------------------------------------

class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ConversationTestCase(BaseModel):
    id: str
    turns: list[Turn]
    expected_output: str | None = None
    metadata: dict = {}
