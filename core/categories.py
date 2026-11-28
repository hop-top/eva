# core/categories.py
"""Per-category scoring over per-case outcomes.

A case names its category in ``metadata.category`` and the date it was added
in ``metadata.added`` (ISO date). One outcome per case; the same summaries
serve a live run and a stored run.
"""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel

# Bucket for cases without ``metadata.category``.
UNCATEGORISED = "uncategorised"


class CategoryScore(BaseModel):
    passed: int = 0
    total: int = 0


class SinceScore(BaseModel):
    since: str
    passed: int = 0
    total: int = 0
    # Scored cases left out because they carry no usable ``metadata.added``.
    excluded: int = 0


class CaseOutcome(BaseModel):
    test_id: str
    category: str | None = None
    added: str | None = None  # ISO date (YYYY-MM-DD)
    # False when no evaluator applied to the case: neither passed nor failed.
    scored: bool = True
    # Scored and every evaluator result passed.
    passed: bool = False


def case_labels(metadata: dict | None) -> tuple[str | None, str | None]:
    """(category, added) from a case's metadata; both normalised to str."""
    md = metadata or {}
    category = md.get("category")
    added = md.get("added")
    if isinstance(added, dt.datetime):
        added = added.date()
    if isinstance(added, dt.date):
        added = added.isoformat()
    return (
        None if category is None else str(category),
        None if added is None else str(added),
    )


def parse_since(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f"--since must be an ISO date (YYYY-MM-DD), got {value!r}")


def _added_date(added: str | None) -> dt.date | None:
    if not added:
        return None
    try:
        return dt.date.fromisoformat(added[:10])
    except ValueError:
        return None


def category_scores(cases: list[CaseOutcome]) -> dict[str, CategoryScore]:
    """passed/total per category over scored cases, first-seen order."""
    out: dict[str, CategoryScore] = {}
    for c in cases:
        if not c.scored:
            continue
        s = out.setdefault(c.category or UNCATEGORISED, CategoryScore())
        s.total += 1
        s.passed += 1 if c.passed else 0
    return out


def since_score(cases: list[CaseOutcome], since: dt.date) -> SinceScore:
    """Accuracy on scored cases added on or after ``since``."""
    res = SinceScore(since=since.isoformat())
    for c in cases:
        if not c.scored:
            continue
        added = _added_date(c.added)
        if added is None:
            res.excluded += 1
        elif added >= since:
            res.total += 1
            res.passed += 1 if c.passed else 0
    return res


def unscored_count(cases: list[CaseOutcome]) -> int:
    return sum(1 for c in cases if not c.scored)


def format_figures(
    cases: list[CaseOutcome], since: dt.date | None = None
) -> list[str]:
    """Plain-text lines shared by `run` and `runs show`."""
    lines: list[str] = []
    scores = category_scores(cases)
    if any(c.category for c in cases):
        lines.append("By category:")
        for name, s in scores.items():
            lines.append(f"  {name}: {s.passed}/{s.total}")
    if since is not None:
        s = since_score(cases, since)
        lines.append(
            f"Since {s.since}: {s.passed}/{s.total} "
            f"({s.excluded} without added date excluded)"
        )
    n = unscored_count(cases)
    if n:
        lines.append(f"{n} not scored (no evaluator applied); excluded from all figures")
    return lines
