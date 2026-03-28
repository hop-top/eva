# core/redaction.py — Content redaction, truncation, and retention helpers.
# Self-contained: no imports from other core modules to avoid circular deps.
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.storage import SqliteStorage

_REDACTED = "[REDACTED]"


def redact_artifact(content: str, policy: list[str]) -> str:
    """Replace all regex matches from *policy* with ``[REDACTED]``.

    Args:
        content: Raw artifact text to sanitise.
        policy: List of regex pattern strings. Each is compiled with
                ``re.DOTALL`` so ``.`` matches newlines too.

    Returns:
        Sanitised copy of *content*; original is never mutated.
    """
    for pattern in policy:
        content = re.sub(pattern, _REDACTED, content, flags=re.DOTALL)
    return content


def should_truncate(size_bytes: int, max_bytes: int) -> bool:
    """Return True when *size_bytes* exceeds *max_bytes*.

    Args:
        size_bytes: Actual payload size.
        max_bytes:  Configured ceiling (0 means never truncate).
    """
    if max_bytes <= 0:
        return False
    return size_bytes > max_bytes


def apply_retention(storage: "SqliteStorage", ttl_days: int) -> int:
    """Delete ArtifactRecord rows older than *ttl_days*.

    Args:
        storage:  Live SqliteStorage instance.
        ttl_days: Rows whose ``created_at`` is before
                  ``now - ttl_days`` are removed. 0 means no-op.

    Returns:
        Number of rows deleted.
    """
    if ttl_days <= 0:
        return 0

    from sqlmodel import Session, delete
    from core.storage import ArtifactRecord  # local import avoids circular at module level

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=ttl_days)

    with Session(storage.engine) as session:
        stmt = (
            delete(ArtifactRecord)  # type: ignore[arg-type]
            .where(ArtifactRecord.created_at < cutoff)  # type: ignore[attr-defined]
        )
        result = session.exec(stmt)  # type: ignore[call-overload]
        session.commit()
        return result.rowcount  # type: ignore[union-attr]
