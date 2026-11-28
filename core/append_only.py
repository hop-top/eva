# core/append_only.py
"""Append-only datasets: cases are never edited or removed.

A dataset opts in with ``append_only: true`` (YAML dataset, or the
``dataset.yaml`` manifest of a directory dataset). Eva then keeps a ledger
of ``case id -> case_hash`` next to the dataset, tracked in git with it:

- YAML dataset ``suite.yaml``      -> ``suite.lock.json``
- directory dataset ``cases/``     -> ``cases/dataset.lock.json``

``check`` fails when a recorded case changed or disappeared, when ids
collide, when a case is not yet recorded, when provenance metadata is
missing, or when a ``supersedes`` reference is invalid. A wrong case is
never edited: a new case with ``supersedes: <old id>`` replaces it, and
the old case stays in the dataset but drops out of scoring.
"""
from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from core.dataset import EvaTestCase, case_hash, read_directory

LEDGER_VERSION = 1
LEDGER_ALGORITHM = "sha256"
REQUIRED_PROVENANCE = ("source", "licence", "added", "origin")
ORIGINS = ("import", "failure", "handwritten")


class NotAppendOnly(ValueError):
    """The dataset does not declare ``append_only: true``."""


@dataclass
class Problem:
    code: str  # edited | removed | collision | unrecorded | provenance | supersedes | conflict | invalid
    id: str | None
    message: str

    def as_dict(self) -> dict:
        return {"code": self.code, "id": self.id, "message": self.message}


@dataclass
class CheckResult:
    cases: int = 0
    scored: int = 0
    superseded: int = 0
    unrecorded: list[str] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def ledger_path(path: Path) -> Path:
    path = Path(path)
    if path.is_dir():
        return path / "dataset.lock.json"
    return path.with_name(path.stem + ".lock.json")


def read_ledger(path: Path) -> dict[str, str]:
    p = ledger_path(path)
    if not p.exists():
        return {}
    data = json.loads(p.read_text())
    return dict(data.get("cases", {}))


def write_ledger(path: Path, hashes: dict[str, str]) -> None:
    # one line per case id: small diffs, clean merges
    lines = [
        f"  {json.dumps(k, ensure_ascii=False)}: {json.dumps(v)}"
        for k, v in sorted(hashes.items())
    ]
    body = ",\n".join(lines)
    text = (
        '{\n "version": %d,\n "algorithm": "%s",\n "cases": {%s}\n}\n'
        % (LEDGER_VERSION, LEDGER_ALGORITHM, ("\n" + body + "\n ") if lines else "")
    )
    ledger_path(path).write_text(text)


def read_source(path: Path) -> tuple[dict, list[EvaTestCase]]:
    """Settings (everything but ``tests``) and cases; needs no target."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")
    if path.is_dir():
        return read_directory(path)
    if path.suffix == ".jsonl":
        return read_directory_file(path)
    raw = yaml.safe_load(path.read_text()) or {}
    tests = [EvaTestCase.model_validate(t) for t in raw.pop("tests", [])]
    return raw, tests


def read_directory_file(path: Path) -> tuple[dict, list[EvaTestCase]]:
    tests = []
    for n, line in enumerate(path.read_text().splitlines(), 1):
        if line.strip():
            try:
                tests.append(EvaTestCase.model_validate(json.loads(line)))
            except ValueError as e:
                raise ValueError(f"{path.name}:{n}: {e}") from None
    return {}, tests


def provenance_problems(case: EvaTestCase) -> list[Problem]:
    out = []
    meta = case.metadata or {}
    for k in REQUIRED_PROVENANCE:
        if meta.get(k) in (None, ""):
            out.append(Problem("provenance", case.id, f"{case.id}: metadata.{k} missing"))
    origin = meta.get("origin")
    if origin and origin not in ORIGINS:
        out.append(Problem(
            "provenance", case.id,
            f"{case.id}: metadata.origin must be one of {', '.join(ORIGINS)}",
        ))
    added = meta.get("added")
    if added not in (None, ""):
        try:
            if isinstance(added, datetime.date):
                pass
            else:
                datetime.date.fromisoformat(str(added))
        except ValueError:
            out.append(Problem(
                "provenance", case.id,
                f"{case.id}: metadata.added must be an ISO date (YYYY-MM-DD)",
            ))
    return out


def analyse(cases: list[EvaTestCase], ledger: dict[str, str]) -> CheckResult:
    """Every reason the dataset is not sound. Pure: no I/O."""
    res = CheckResult(cases=len(cases))
    first: dict[str, EvaTestCase] = {}
    for c in cases:
        if c.id in first:
            res.problems.append(Problem("collision", c.id, f"{c.id}: id used by more than one case"))
        else:
            first[c.id] = c
    for cid, h in sorted(ledger.items()):
        if cid not in first:
            res.problems.append(Problem(
                "removed", cid, f"{cid}: recorded case removed from the dataset"))
        elif case_hash(first[cid]) != h:
            res.problems.append(Problem(
                "edited", cid,
                f"{cid}: content changed since it was recorded "
                "(add a new case with supersedes: instead of editing)"))
    for cid in first:
        if cid not in ledger:
            res.unrecorded.append(cid)
            res.problems.append(Problem(
                "unrecorded", cid, f"{cid}: not in the ledger (run `eva dataset lock`)"))
    for c in first.values():
        res.problems.extend(provenance_problems(c))
    gone: set[str] = set()
    for c in first.values():
        if not c.supersedes:
            continue
        if c.supersedes == c.id:
            res.problems.append(Problem("supersedes", c.id, f"{c.id}: supersedes itself"))
        elif c.supersedes not in first:
            res.problems.append(Problem(
                "supersedes", c.id, f"{c.id}: supersedes unknown case {c.supersedes}"))
        else:
            gone.add(c.supersedes)
    for c in first.values():  # a supersedes-cycle would leave nothing scored
        seen, cur = {c.id}, c
        while cur.supersedes and cur.supersedes in first and cur.supersedes != cur.id:
            cur = first[cur.supersedes]
            if cur.id in seen:
                res.problems.append(Problem(
                    "supersedes", c.id, f"{c.id}: supersedes cycle through {cur.id}"))
                break
            seen.add(cur.id)
    res.superseded = len(gone)
    res.scored = len(first) - len(gone)
    return res


def _load(path: Path) -> tuple[list[EvaTestCase], dict[str, str]]:
    settings, cases = read_source(path)
    if not settings.get("append_only"):
        raise NotAppendOnly(f"{path}: not append-only (set append_only: true)")
    return cases, read_ledger(path)


def check(path: Path) -> CheckResult:
    cases, ledger = _load(Path(path))
    return analyse(cases, ledger)


def lock(path: Path, dry_run: bool = False) -> tuple[CheckResult, list[str]]:
    """Record unrecorded cases in the ledger. Refuses (writes nothing) on any
    problem other than the cases being unrecorded. Returns (result, recorded ids)."""
    path = Path(path)
    cases, ledger = _load(path)
    res = analyse(cases, ledger)
    blocking = [p for p in res.problems if p.code != "unrecorded"]
    if blocking:
        res.problems = blocking
        return res, []
    new = {c.id: case_hash(c) for c in cases if c.id in set(res.unrecorded)}
    if new and not dry_run:
        write_ledger(path, {**ledger, **new})
    res.problems = []
    res.unrecorded = []
    return res, list(new)


def add(
    path: Path, raw_cases: list[dict], file: str | None = None, dry_run: bool = False
) -> tuple[list[str], list[str], list[Problem]]:
    """Append cases to a directory dataset and record them.

    Returns (added ids, skipped ids, problems). An id already present with
    the same case hash is skipped (re-adding is a no-op); with a different
    hash it is refused. Nothing is written when any problem is found.
    """
    path = Path(path)
    if not path.is_dir():
        raise ValueError("add works on directory datasets")
    cases, ledger = _load(path)
    base = analyse(cases, ledger)
    if base.problems:
        return [], [], base.problems
    have = {c.id: case_hash(c) for c in cases}
    fresh_raw: list[dict] = []
    fresh: list[EvaTestCase] = []
    added, skipped, problems = [], [], []
    for raw in raw_cases:
        try:
            case = EvaTestCase.model_validate(raw)
        except ValueError as e:
            problems.append(Problem("invalid", raw.get("id") if isinstance(raw, dict) else None, str(e)))
            continue
        h = case_hash(case)
        if case.id in have:
            if have[case.id] == h:
                skipped.append(case.id)
            else:
                problems.append(Problem(
                    "conflict", case.id,
                    f"{case.id}: already in the dataset with different content"))
            continue
        have[case.id] = h
        fresh_raw.append(raw)
        fresh.append(case)
        added.append(case.id)
    if problems:
        return [], [], problems
    after = analyse(cases + fresh, {**ledger, **{c.id: case_hash(c) for c in fresh}})
    if after.problems:
        return [], [], after.problems
    target = _target_file(path, file) if fresh else None
    if fresh and not dry_run:
        text = target.read_text() if target.exists() else ""
        out = text if (not text or text.endswith("\n")) else text + "\n"
        out += "".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in fresh_raw)
        target.write_text(out)
        write_ledger(path, {**ledger, **{c.id: case_hash(c) for c in fresh}})
    return added, skipped, []


def _target_file(path: Path, file: str | None) -> Path:
    if file is None:
        existing = sorted(path.glob("*.jsonl"))
        if len(existing) != 1:
            raise ValueError("--file required: the directory does not hold exactly one .jsonl file")
        return existing[0]
    if Path(file).name != file or not file.endswith(".jsonl"):
        raise ValueError("--file must be a plain *.jsonl file name")
    return path / file
