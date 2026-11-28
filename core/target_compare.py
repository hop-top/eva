# core/target_compare.py
"""Two targets on the cases both have answered, from stored per-case results.

Pure logic over ``CaseResult`` records; no storage, no CLI. A case is shared
when both targets hold a record for it under the same case hash. A case
answered under different hashes by the two sides is not shared (the sides
saw different text) and is counted in ``excluded.hash_mismatch``.
"""
from __future__ import annotations

import datetime as dt
from typing import Iterable, NamedTuple

from core.categories import UNCATEGORISED, _added_date

OVERALL = "overall"


class CaseInfo(NamedTuple):
    """A current scored case of the dataset file."""
    case_hash: str  # "sha256:<hex>"
    category: str | None
    added: str | None


def _bucket() -> dict:
    return {"shared": 0, "left_passed": 0, "right_passed": 0,
            "left_rate": None, "right_rate": None, "diff": None,
            "only_left": [], "only_right": []}


def _finish(b: dict) -> dict:
    b["only_left"].sort()
    b["only_right"].sort()
    if b["shared"]:
        b["left_rate"] = round(b["left_passed"] / b["shared"], 4)
        b["right_rate"] = round(b["right_passed"] / b["shared"], 4)
        b["diff"] = round(b["right_rate"] - b["left_rate"], 4)
    return b


def _add(b: dict, case: str, lp: bool, rp: bool) -> None:
    b["shared"] += 1
    b["left_passed"] += lp
    b["right_passed"] += rp
    if lp and not rp:
        b["only_left"].append(case)
    if rp and not lp:
        b["only_right"].append(case)


def compare_targets(
    left: Iterable, right: Iterable, *,
    current: dict[str, CaseInfo] | None = None,
    since: dt.date | None = None,
) -> dict:
    """Compare two targets' records (one dataset). ``left``/``right`` are
    ``CaseResult`` lists. ``current`` (case id -> CaseInfo, from the dataset
    file) gives categories and ``added`` dates; without it there is one
    overall bucket and no categories."""
    lm = {(r.case, r.case_hash): r for r in left}
    rm = {(r.case, r.case_hash): r for r in right}
    shared = sorted(lm.keys() & rm.keys())
    shared_cases = {c for c, _ in shared}
    l_cases = {c for c, _ in lm}
    r_cases = {c for c, _ in rm}
    both = l_cases & r_cases

    overall = _bucket()
    cats: dict[str, dict] = {}
    since_b = _bucket() if since is not None else None
    no_added = 0
    for case, h in shared:
        lp, rp = lm[(case, h)].passed, rm[(case, h)].passed
        _add(overall, case, lp, rp)
        info = current.get(case) if current is not None else None
        if current is not None:
            _add(cats.setdefault((info.category if info else None) or UNCATEGORISED,
                                 _bucket()), case, lp, rp)
        if since_b is not None:
            added = _added_date(info.added) if info else None
            if added is None:
                no_added += 1
            elif added >= since:
                _add(since_b, case, lp, rp)

    out = {
        "categorised": current is not None,
        "overall": _finish(overall),
        "categories": {k: _finish(v) for k, v in sorted(cats.items())},
        "excluded": {
            "hash_mismatch": len(both - shared_cases),
            "left_only": len(l_cases - r_cases),
            "right_only": len(r_cases - l_cases),
        },
    }
    if since_b is not None:
        out["since"] = {"date": since.isoformat(), **_finish(since_b),
                        "excluded_no_added": no_added}
    return out
