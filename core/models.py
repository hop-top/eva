# core/models.py
from __future__ import annotations
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, model_validator


class Score(BaseModel):
    value: float
    reason: str | None = None
    metadata: dict = {}


class EvaluatorRef(BaseModel):
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
