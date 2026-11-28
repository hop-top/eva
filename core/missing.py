# core/missing.py
"""Select the cases a target has no stored result for (``eva run --missing``).

A result is stored per (dataset, target id, case id, case hash) and the first
one stands, so "has a result" means a record for the case at its CURRENT hash.
A case edited since (new hash) is missing again; superseded cases are never
selected. Cases whose target call failed, and cases no evaluator applied to,
are never recorded, so they are selected again.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.adapters import CaseResultStore
from core.case_results import hash_of
from core.categories import case_labels
from core.dataset import Dataset, EvaTestCase, case_hash


@dataclass
class MissingSelection:
    scored: int  # cases the dataset runs (superseded ones excluded)
    missing: int  # of those, missing for the target, after the category filter
    selected: list[EvaTestCase] = field(default_factory=list)  # after the limit

    @property
    def ids(self) -> list[str]:
        return [t.id for t in self.selected]


def select_missing(
    dataset: Dataset,
    storage: object,
    category: str | None = None,
    limit: int | None = None,
) -> MissingSelection:
    """Cases of ``dataset`` the dataset's target has no stored result for.

    ``category`` keeps cases whose ``metadata.category`` equals it; ``limit``
    keeps the first N missing cases in dataset order. Raises ``ValueError``
    when ``storage`` cannot hold per-case results or ``limit`` is below 1.
    """
    if not isinstance(storage, CaseResultStore):
        raise ValueError(
            "--missing needs a storage that keeps per-case results; "
            f"{type(storage).__name__} does not"
        )
    if limit is not None and limit < 1:
        raise ValueError(f"limit must be at least 1, got {limit}")
    scored = dataset.scored_tests()
    have = {
        (r.case, r.case_hash)
        for r in storage.get_case_results(dataset.name, dataset.result_target_id)
    }
    missing = [t for t in scored if (t.id, hash_of(case_hash(t))) not in have]
    if category is not None:
        missing = [t for t in missing if case_labels(t.metadata)[0] == category]
    return MissingSelection(
        scored=len(scored),
        missing=len(missing),
        selected=missing if limit is None else missing[:limit],
    )
