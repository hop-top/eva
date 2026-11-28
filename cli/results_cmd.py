# cli/results_cmd.py
"""``eva results`` — per-case results per target: list, export, import.

Exit codes: 0 ok (including nothing to do); 1 conflicts found (import or
export: two different results for one case, the earlier one is kept);
2 bad input (bad flag or --format, malformed or unsupported JSONL, dataset
file unreadable or with duplicate case ids).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

results_app = typer.Typer(help="Per-case results per target: list, export, import.")

_FORMAT = typer.Option("text", "--format", help="text | json")
_DB = typer.Option(None, "--db", help="Path to SQLite DB file.")
_DATASET = typer.Option(..., "--dataset", help="Dataset name as stored with the results.")
_DATASET_FILE = typer.Option(
    None, "--dataset-file",
    help="Dataset file or directory: keep only its current scored cases "
    "(superseded or changed cases drop out); refuse duplicate case ids.",
)


def _fail(msg: str, code: int = 2):
    typer.echo(f"Error: {msg}", err=True)
    raise typer.Exit(code)


def _fmt(fmt: str) -> str:
    if fmt not in ("text", "json"):
        _fail("--format must be 'text' or 'json'")
    return fmt


def _storage(db: Optional[str]):
    from core.storage import SqliteStorage

    return SqliteStorage(db_url=f"sqlite:///{db}" if db else "sqlite:///.eva/state.db")


def _json(payload: dict) -> None:
    typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))


def _select(storage, dataset, target, dataset_file):
    recs = storage.get_case_results(dataset, target_id=target)
    if dataset_file is None:
        return recs
    from core.case_results import hash_of
    from core.dataset import case_hash, load_dataset

    try:
        ds = load_dataset(dataset_file, target="http://unused.invalid")
    except (ValueError, FileNotFoundError) as e:
        _fail(str(e))
    ids = [t.id for t in ds.tests]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        _fail(f"duplicate case ids in {dataset_file}: {', '.join(dupes)}")
    current = {(t.id, hash_of(case_hash(t))) for t in ds.scored_tests()}
    return [r for r in recs if (r.case, r.case_hash) in current]


@results_app.command("list")
def results_list(
    dataset: str = _DATASET,
    target: Optional[str] = typer.Option(None, "--target", help="Target id."),
    status: Optional[str] = typer.Option(None, "--status", help="pass | fail"),
    limit: int = typer.Option(1000, "--limit", help="Max records."),
    dataset_file: Optional[Path] = _DATASET_FILE,
    db: Optional[str] = _DB,
    fmt: str = _FORMAT,
) -> None:
    """One record per case and target: passed, score, evaluator reasons,
    run id, date, case hash."""
    fmt = _fmt(fmt)
    if status not in (None, "pass", "fail"):
        _fail("--status must be 'pass' or 'fail'")
    recs = _select(_storage(db), dataset, target, dataset_file)
    if status:
        recs = [r for r in recs if r.passed == (status == "pass")]
    recs = recs[:limit]
    if fmt == "json":
        _json({"results": [r.model_dump() for r in recs]})
        return
    if not recs:
        typer.echo("No results found.")
        return
    from rich.console import Console
    from rich.table import Table

    t = Table(title="Case results")
    for c in ("Target", "Case", "Pass", "Score", "Run", "At", "Hash"):
        t.add_column(c)
    for r in recs:
        t.add_row(r.target_id, r.case, "pass" if r.passed else "fail",
                  "" if r.score is None else f"{r.score:.2f}", r.run_id,
                  r.at[:19], r.case_hash[7:19])
    Console().print(t)


def _report_conflicts(conflicts: list[dict]) -> None:
    for c in conflicts:
        typer.echo(
            f"conflict: {c['dataset']} {c['target_id']} {c['case']}: kept run "
            f"{c['kept_run_id']}, other run {c['other_run_id']}", err=True)


@results_app.command("export")
def results_export(
    dataset: str = _DATASET,
    dir: Path = typer.Option(..., "--dir", help="Directory to write JSONL files into."),
    target: Optional[str] = typer.Option(None, "--target", help="Target id."),
    dataset_file: Optional[Path] = _DATASET_FILE,
    dry_run: bool = typer.Option(False, "--dry-run", help="Report; write nothing."),
    db: Optional[str] = _DB,
    fmt: str = _FORMAT,
) -> None:
    """Write results as JSONL, one file per dataset and target."""
    from core.case_results import CaseResultFormatError, export_records

    fmt = _fmt(fmt)
    recs = _select(_storage(db), dataset, target, dataset_file)
    try:
        rep = export_records(recs, dir, dry_run=dry_run)
    except CaseResultFormatError as e:
        _fail(str(e))
    if fmt == "json":
        _json(rep)
    else:
        verb = "would write" if dry_run else "wrote"
        for f in rep["files"]:
            typer.echo(f"{verb} {f['records']} record(s): {f['path']}")
        if not rep["files"]:
            typer.echo("Nothing to export.")
    _report_conflicts(rep["conflicts"])
    raise typer.Exit(1 if rep["conflicts"] else 0)


@results_app.command("import")
def results_import(
    paths: list[Path] = typer.Argument(..., help="JSONL files or directories."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report; write nothing."),
    db: Optional[str] = _DB,
    fmt: str = _FORMAT,
) -> None:
    """Merge exported results into the local store (first result stands)."""
    from core.case_results import CaseResultFormatError, import_records, load_jsonl

    fmt = _fmt(fmt)
    try:
        recs = load_jsonl(paths)
    except CaseResultFormatError as e:
        _fail(str(e))
    rep = import_records(_storage(db), recs, dry_run=dry_run)
    if fmt == "json":
        _json(rep)
    else:
        verb = "would insert" if dry_run else "inserted"
        typer.echo(
            f"{verb} {rep['inserted']}, unchanged {rep['unchanged']}, "
            f"replaced {rep['replaced']}, conflicts {len(rep['conflicts'])}, "
            f"hash mismatches {len(rep['hash_mismatches'])}"
        )
    _report_conflicts(rep["conflicts"])
    for m in rep["hash_mismatches"]:
        typer.echo(f"hash mismatch: {m['dataset']} {m['target_id']} {m['case']}", err=True)
    raise typer.Exit(1 if rep["conflicts"] else 0)
