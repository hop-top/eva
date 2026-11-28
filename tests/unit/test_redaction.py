# tests/unit/test_redaction.py
"""core.redaction: pattern redaction and artifact retention."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session, select

from core.redaction import apply_retention, redact_artifact
from core.storage import ArtifactRecord, SqliteStorage


@pytest.fixture
def storage(tmp_path):
    return SqliteStorage(db_url=f"sqlite:///{tmp_path}/test_redaction.db")


# ---------------------------------------------------------------------------
# redact_artifact
# ---------------------------------------------------------------------------


def test_redact_artifact_scrubs_matches_and_keeps_the_rest():
    content = '{"api_key": "sk-supersecret123", "query": "hello"}'
    result = redact_artifact(content, [r'"api_key"\s*:\s*"[^"]+"'])
    assert result == '{[REDACTED], "query": "hello"}'


def test_redact_artifact_multiple_patterns():
    content = "token: Bearer abc123\nemail: user@example.com"
    patterns = [
        r"Bearer\s+\S+",
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    ]
    result = redact_artifact(content, patterns)
    assert result == "token: [REDACTED]\nemail: [REDACTED]"


def test_redact_artifact_replaces_every_match_of_a_pattern():
    assert redact_artifact("k=1 k=2 k=3", [r"k=\d"]) == "[REDACTED] [REDACTED] [REDACTED]"


def test_redact_artifact_dot_matches_newlines():
    assert redact_artifact("a\nSECRET\nb", [r"SECRET.b"]) == "a\n[REDACTED]"


@pytest.mark.parametrize(
    "content,patterns",
    [
        ('{"api_key": "sk-secret"}', []),
        ('{"q": "hello"}', [r'"api_key"\s*:\s*"[^"]+"']),
    ],
)
def test_redact_artifact_unchanged_without_match(content, patterns):
    assert redact_artifact(content, patterns) == content


# ---------------------------------------------------------------------------
# apply_retention
# ---------------------------------------------------------------------------


def _insert_artifact(storage: SqliteStorage, artifact_id: str, age_days: int) -> None:
    ts = datetime.now(tz=timezone.utc) - timedelta(days=age_days)
    with Session(storage.engine) as session:
        session.add(
            ArtifactRecord(
                artifact_id=artifact_id,
                kind="request",
                content_type="application/json",
                storage_backend="inline",
                json_content="{}",
                created_at=ts,
            )
        )
        session.commit()


def _remaining(storage: SqliteStorage) -> set[str]:
    with Session(storage.engine) as session:
        return {r.artifact_id for r in session.exec(select(ArtifactRecord)).all()}


def test_apply_retention_deletes_only_rows_older_than_ttl(storage):
    for aid, age in (("old-1", 91), ("old-2", 120), ("recent-1", 10), ("recent-2", 1)):
        _insert_artifact(storage, aid, age_days=age)

    assert apply_retention(storage, ttl_days=90) == 2
    assert _remaining(storage) == {"recent-1", "recent-2"}


def test_apply_retention_zero_ttl_keeps_everything(storage):
    _insert_artifact(storage, "very-old", age_days=3650)
    assert apply_retention(storage, ttl_days=0) == 0
    assert _remaining(storage) == {"very-old"}


def test_apply_retention_is_idempotent(storage):
    _insert_artifact(storage, "stale", age_days=100)
    assert apply_retention(storage, ttl_days=30) == 1
    assert apply_retention(storage, ttl_days=30) == 0
