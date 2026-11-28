# core/case_results.py
"""Per-case results: one record per (dataset, target, case, case hash).

A record stays valid because append-only cases never change; the first
result for a key stands. Upstream errors (the target never answered) and
cases no evaluator applied to are not recorded, so they are retried.

Durable form: JSONL, one file per (dataset, target), one record per line
(see ``export_records`` / ``import_records``).
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

from pydantic import BaseModel

if TYPE_CHECKING:
    from core.adapters import CaseResultStore

SCHEMA_VERSION = 1
HASH_PREFIX = "sha256:"
# Pseudo-evaluator the runner adds when the target call failed.
UPSTREAM_EVALUATOR = "target"


class CaseResultFormatError(ValueError):
    """Malformed or unsupported JSONL input."""


class EvaluatorOutcome(BaseModel):
    name: str
    passed: bool
    score: float | None = None
    reason: str | None = None
    mode: str | None = None


class CaseResult(BaseModel):
    v: int = SCHEMA_VERSION
    dataset: str
    target_id: str
    case: str
    case_hash: str  # "sha256:<hex>", hex from core.dataset.case_hash
    passed: bool
    score: float | None = None
    evaluators: list[EvaluatorOutcome] = []
    run_id: str
    at: str  # UTC ISO-8601 start of the run that produced it
    provider: str | None = None
    model: str | None = None

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (self.dataset, self.target_id, self.case, self.case_hash)

    def payload(self) -> dict:
        """What was observed, ignoring which run saw it and when."""
        d = self.model_dump()
        for k in ("run_id", "at"):
            d.pop(k)
        return d

    def order(self) -> tuple[str, str]:
        return (self.at, self.run_id)


def is_upstream_error(evaluators: Iterable[str], invocation_error: bool = False) -> bool:
    return invocation_error or UPSTREAM_EVALUATOR in set(evaluators)


def hash_of(case_hash_hex: str) -> str:
    return HASH_PREFIX + case_hash_hex


def dump_line(rec: CaseResult) -> str:
    return json.dumps(rec.model_dump(), sort_keys=True, ensure_ascii=False)


def _sort_key(r: CaseResult):
    return (r.dataset, r.target_id, r.case, r.case_hash, r.at, r.run_id)


def sorted_records(recs: Iterable[CaseResult]) -> list[CaseResult]:
    return sorted(recs, key=_sort_key)


def earlier(a: CaseResult, b: CaseResult) -> CaseResult:
    return a if a.order() <= b.order() else b


# ---------------------------------------------------------------------------
# JSONL files
# ---------------------------------------------------------------------------

def _slug(text: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", text).strip(".") or "_"
    return f"{safe[:80]}-{hashlib.sha256(text.encode()).hexdigest()[:8]}"


def file_for(root: Path, dataset: str, target_id: str) -> Path:
    return Path(root) / _slug(dataset) / f"{_slug(target_id)}.jsonl"


def load_jsonl(paths: Iterable[Path]) -> list[CaseResult]:
    """Read records from files and directories (``*.jsonl``, recursive).

    Any malformed line or unknown schema version aborts the whole read.
    """
    files: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            files.extend(sorted(p.rglob("*.jsonl")))
        elif p.is_file():
            files.append(p)
        else:
            raise CaseResultFormatError(f"{p}: not found")
    out: list[CaseResult] = []
    for f in files:
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                if not isinstance(data, dict):
                    raise ValueError("record must be a JSON object")
                if data.get("v") != SCHEMA_VERSION:
                    raise CaseResultFormatError(
                        f"{f}:{n}: unsupported record version {data.get('v')!r} "
                        f"(expected {SCHEMA_VERSION})"
                    )
                out.append(CaseResult.model_validate(data))
            except CaseResultFormatError:
                raise
            except ValueError as e:
                raise CaseResultFormatError(f"{f}:{n}: {e}") from None
    return out


def _conflict(winner: CaseResult, loser: CaseResult) -> dict:
    return {
        "dataset": winner.dataset, "target_id": winner.target_id,
        "case": winner.case, "case_hash": winner.case_hash,
        "kept_run_id": winner.run_id, "other_run_id": loser.run_id,
    }


def export_records(
    records: Iterable[CaseResult], root: Path, dry_run: bool = False
) -> dict:
    """Write records to ``<root>/<dataset>/<target>.jsonl``.

    An existing file is merged, not replaced: records it holds that the
    store lacks are kept; a key present in both with different content
    keeps the earlier record and is reported as a conflict. Files are
    sorted, so re-exporting an unchanged store is byte-identical.
    """
    groups: dict[tuple[str, str], dict[tuple, CaseResult]] = {}
    conflicts: list[dict] = []
    for r in records:
        g = groups.setdefault((r.dataset, r.target_id), {})
        _merge_into(g, r, conflicts)
    files = []
    for (ds, tid), g in sorted(groups.items()):
        path = file_for(root, ds, tid)
        if path.exists():
            for old in load_jsonl([path]):
                _merge_into(g, old, conflicts)
        recs = sorted_records(g.values())
        files.append({"path": str(path), "records": len(recs)})
        if not dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("".join(dump_line(r) + "\n" for r in recs), encoding="utf-8")
    return {"dry_run": dry_run, "files": files, "conflicts": conflicts}


def _merge_into(group: dict, rec: CaseResult, conflicts: list[dict]) -> None:
    have = group.get(rec.key)
    if have is None:
        group[rec.key] = rec
        return
    if have.payload() == rec.payload():
        group[rec.key] = earlier(have, rec)
        return
    win = earlier(have, rec)
    lose = rec if win is have else have
    conflicts.append(_conflict(win, lose))
    group[rec.key] = win


def import_records(
    store: "CaseResultStore", records: Iterable[CaseResult], dry_run: bool = False
) -> dict:
    """Merge records into a store; first-result-stands, earlier wins conflicts.

    Same key, same content: no-op. Same key, different content: the record
    with the earlier (at, run_id) is kept and the pair reported. Same case
    under another hash: both kept, reported as a hash mismatch.
    """
    inserted = unchanged = replaced = 0
    conflicts: list[dict] = []
    mismatches: dict[tuple, set[str]] = {}
    # (dataset, target, case) -> {hash: record}, local state plus this import
    seen: dict[tuple, dict[str, CaseResult]] = {}

    def local(r: CaseResult) -> dict[str, CaseResult]:
        k = (r.dataset, r.target_id, r.case)
        if k not in seen:
            seen[k] = {
                x.case_hash: x
                for x in store.get_case_results(r.dataset, r.target_id, [r.case])
            }
        return seen[k]

    for r in records:
        by_hash = local(r)
        for h in by_hash:
            if h != r.case_hash:
                mismatches.setdefault((r.dataset, r.target_id, r.case), set()).update(
                    {h, r.case_hash}
                )
        have = by_hash.get(r.case_hash)
        if have is None:
            by_hash[r.case_hash] = r
            inserted += 1
            if not dry_run:
                store.put_case_results([r])
        elif have.payload() == r.payload():
            unchanged += 1
        else:
            win = earlier(have, r)
            lose = r if win is have else have
            conflicts.append(_conflict(win, lose))
            if win is r:
                replaced += 1
                by_hash[r.case_hash] = r
                if not dry_run:
                    store.replace_case_result(r)
    return {
        "dry_run": dry_run,
        "inserted": inserted,
        "unchanged": unchanged,
        "replaced": replaced,
        "conflicts": conflicts,
        "hash_mismatches": [
            {"dataset": d, "target_id": t, "case": c, "hashes": sorted(hs)}
            for (d, t, c), hs in sorted(mismatches.items())
        ],
    }


def build_record(
    *, dataset: str, target_id: str, case: str, case_hash_hex: str,
    results: list[Any], run_id: str, at: str,
    provider: str | None = None, model: str | None = None,
) -> CaseResult | None:
    """Record for one case from its evaluator ``Result``s, or None when it
    must not be recorded (upstream error, or no evaluator applied)."""
    if not results or is_upstream_error(r.evaluator for r in results):
        return None
    vals = [r.score.value for r in results if isinstance(r.score.value, (int, float))]
    return CaseResult(
        dataset=dataset, target_id=target_id, case=case,
        case_hash=hash_of(case_hash_hex),
        passed=all(r.passed for r in results),
        score=(sum(vals) / len(vals)) if vals else None,
        evaluators=[
            EvaluatorOutcome(name=r.evaluator, passed=r.passed,
                             score=r.score.value, reason=r.score.reason, mode=r.mode)
            for r in results
        ],
        run_id=run_id, at=at, provider=provider, model=model,
    )
