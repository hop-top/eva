# cli/dataset_cmd.py
"""``eva dataset`` — integrity commands for append-only datasets.

Exit codes: 0 ok, 2 usage / bad input / dataset not append-only,
3 integrity check failed (edited, removed, colliding, unrecorded or
provenance-less cases; nothing is written).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

dataset_app = typer.Typer(help="Append-only dataset integrity: check, lock, add.")

_PATH = typer.Argument(..., help="Dataset: YAML file or directory of JSONL files.")
_FORMAT = typer.Option("text", "--format", help="text | json")


def _fmt(fmt: str) -> str:
    if fmt not in ("text", "json"):
        typer.echo("Error: --format must be 'text' or 'json'", err=True)
        raise typer.Exit(2)
    return fmt


def _fail(msg: str, code: int = 2):
    typer.echo(f"Error: {msg}", err=True)
    raise typer.Exit(code)


def _emit(fmt: str, payload: dict, text: str, problems) -> None:
    if fmt == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        for p in problems:
            typer.echo(f"problem: {p.message}", err=True)
        typer.echo(text)


@dataset_app.command("check")
def check_cmd(path: Path = _PATH, fmt: str = _FORMAT):
    """Verify no recorded case was edited or removed, ids are unique,
    every case is recorded and carries provenance."""
    from core.append_only import NotAppendOnly, check

    fmt = _fmt(fmt)
    try:
        res = check(path)
    except (NotAppendOnly, ValueError, FileNotFoundError) as e:
        _fail(str(e))
    payload = {
        "ok": res.ok, "cases": res.cases, "scored": res.scored,
        "superseded": res.superseded,
        "problems": [p.as_dict() for p in res.problems],
    }
    _emit(fmt, payload,
          f"{'ok' if res.ok else 'FAILED'}: {res.cases} cases, "
          f"{res.scored} scored, {res.superseded} superseded", res.problems)
    raise typer.Exit(0 if res.ok else 3)


@dataset_app.command("lock")
def lock_cmd(
    path: Path = _PATH,
    dry_run: bool = typer.Option(False, "--dry-run", help="Report; write nothing."),
    fmt: str = _FORMAT,
):
    """Record new cases in the ledger. Refuses if any recorded case was
    edited or removed, ids collide or provenance is missing."""
    from core.append_only import NotAppendOnly, lock

    fmt = _fmt(fmt)
    try:
        res, recorded = lock(path, dry_run=dry_run)
    except (NotAppendOnly, ValueError, FileNotFoundError) as e:
        _fail(str(e))
    payload = {
        "ok": res.ok, "dry_run": dry_run, "recorded": recorded,
        "problems": [p.as_dict() for p in res.problems],
    }
    verb = "would record" if dry_run else "recorded"
    _emit(fmt, payload, f"{'ok' if res.ok else 'FAILED'}: {verb} {len(recorded)} case(s)",
          res.problems)
    raise typer.Exit(0 if res.ok else 3)


@dataset_app.command("add")
def add_cmd(
    path: Path = _PATH,
    source: Path = typer.Option(..., "--from", help="JSONL file of cases to add (or - for stdin)."),
    file: str | None = typer.Option(
        None, "--file", help="Target *.jsonl inside the dataset directory (created if new)."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report; write nothing."),
    fmt: str = _FORMAT,
):
    """Append cases to a directory dataset and record them. A case already
    present with identical content is skipped; same id with different
    content is refused."""
    from core.append_only import NotAppendOnly, add

    fmt = _fmt(fmt)
    try:
        text = sys.stdin.read() if str(source) == "-" else source.read_text()
        raw = [json.loads(ln) for ln in text.splitlines() if ln.strip()]
        added, skipped, problems = add(path, raw, file=file, dry_run=dry_run)
    except (NotAppendOnly, ValueError, FileNotFoundError) as e:
        _fail(str(e))
    payload = {
        "ok": not problems, "dry_run": dry_run, "added": added,
        "skipped": skipped, "problems": [p.as_dict() for p in problems],
    }
    verb = "would add" if dry_run else "added"
    _emit(fmt, payload,
          f"{'ok' if not problems else 'FAILED'}: {verb} {len(added)}, "
          f"skipped {len(skipped)} identical", problems)
    raise typer.Exit(0 if not problems else 3)
