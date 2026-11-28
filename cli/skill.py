# cli/skill.py
"""`eva skill`: serve and install the agent skill bundled with this package.

The skill lives in one folder, `cli/skills/eva-cli`, shipped inside the wheel
and sdist. `show` always reads that bundled copy. `install` copies it out and
records a manifest, so a later install can tell an untouched copy from one a
person edited.
"""
import hashlib
import json
from importlib import resources
from importlib.metadata import PackageNotFoundError, version as _pkg_version
from importlib.resources.abc import Traversable
from pathlib import Path

import typer

SKILL_NAME = "eva-cli"
MANIFEST_NAME = ".skill-install.json"
DEFAULT_DIR = Path("~/.claude/skills") / SKILL_NAME

skill_app = typer.Typer(help="Agent skill bundled with eva.", no_args_is_help=True)


def _eva_version() -> str:
    try:
        return _pkg_version("hop-top-eva")
    except PackageNotFoundError:
        return "0.0.0"


def _root() -> Traversable:
    return resources.files("cli").joinpath("skills", SKILL_NAME)


def _bundled_files() -> dict[str, bytes]:
    """Relative posix path -> content for every file of the bundled skill."""
    out: dict[str, bytes] = {}

    def walk(node: Traversable, prefix: str) -> None:
        for child in sorted(node.iterdir(), key=lambda c: c.name):
            if child.name == "__pycache__":
                continue
            rel = f"{prefix}{child.name}"
            if child.is_dir():
                walk(child, rel + "/")
            else:
                out[rel] = child.read_bytes()

    walk(_root(), "")
    return out


def _reference_names() -> list[str]:
    return sorted(
        p[len("references/"):-len(".md")]
        for p in _bundled_files()
        if p.startswith("references/") and p.endswith(".md") and p.count("/") == 1
    )


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@skill_app.command("show")
def skill_show(
    reference: str = typer.Argument(
        None,
        help="Reference name, without .md. Omit to print SKILL.md.",
        show_default=False,
    ),
):
    """Print the bundled SKILL.md, or one of its references."""
    files = _bundled_files()
    if reference is None:
        rel = "SKILL.md"
    else:
        names = _reference_names()
        if reference not in names:
            raise typer.BadParameter(
                f"unknown reference {reference!r}; valid: {', '.join(names) or '(none)'}",
                param_hint="REFERENCE",
            )
        rel = f"references/{reference}.md"
    typer.echo(files[rel].decode("utf-8"), nl=False)


def _read_manifest(target: Path) -> tuple[dict[str, str] | None, str | None]:
    """Listed files of a valid eva manifest, else (None, why it is not one)."""
    path = target / MANIFEST_NAME
    if not path.is_file():
        return None, "no install manifest"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, "unreadable install manifest"
    if not isinstance(data, dict) or data.get("tool") != "eva":
        return None, "install manifest is not from eva"
    listed = data.get("files")
    if not isinstance(listed, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in listed.items()
    ):
        return None, "malformed install manifest"
    base = target.resolve()
    for rel in listed:
        resolved = (target / rel).resolve()
        if rel == MANIFEST_NAME or base not in resolved.parents:
            return None, f"install manifest lists an unsafe path: {rel}"
    return listed, None


def _existing_files(target: Path) -> list[str]:
    return sorted(
        p.relative_to(target).as_posix()
        for p in target.rglob("*")
        if (p.is_file() or p.is_symlink()) and p.name != MANIFEST_NAME
    ) + ([MANIFEST_NAME] if (target / MANIFEST_NAME).exists() else [])


def _problems(target: Path) -> tuple[dict[str, str], list[str]]:
    """(manifest-listed files, reasons this target must not be overwritten)."""
    existing = _existing_files(target)
    if not existing:
        return {}, []
    listed, why = _read_manifest(target)
    if listed is None:
        return {}, [f"{why}; found: {', '.join(existing)}"]
    problems: list[str] = []
    for rel, digest in sorted(listed.items()):
        f = target / rel
        if not f.is_file():
            problems.append(f"{rel}: missing")
        elif _sha(f.read_bytes()) != digest:
            problems.append(f"{rel}: modified")
    for rel in existing:
        if rel != MANIFEST_NAME and rel not in listed:
            problems.append(f"{rel}: not installed by eva")
    return listed, problems


@skill_app.command("install")
def skill_install(
    dir_: Path = typer.Option(
        DEFAULT_DIR,
        "--dir",
        help="Directory to install into.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print what would be written, replaced or removed; write nothing."
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite a modified or foreign copy. Files eva did not install are kept.",
    ),
):
    """Copy the bundled skill into a directory, with a manifest recording the eva version."""
    target = dir_.expanduser()
    if target.exists() and not target.is_dir():
        typer.echo(f"Error: {target} exists and is not a directory", err=True)
        raise typer.Exit(1)

    bundled = _bundled_files()
    listed, problems = _problems(target) if target.exists() else ({}, [])
    if problems and not force:
        typer.echo(
            f"Error: refusing to overwrite {target}; use --force to replace it:", err=True
        )
        for p in problems:
            typer.echo(f"  {p}", err=True)
        raise typer.Exit(1)
    plan: list[tuple[str, str]] = []
    for rel in bundled:
        plan.append(("replace" if (target / rel).is_file() else "write", rel))
    for rel in sorted(set(listed) - set(bundled)):
        if (target / rel).exists():
            plan.append(("remove", rel))
    plan.append(("replace" if (target / MANIFEST_NAME).is_file() else "write", MANIFEST_NAME))

    if dry_run:
        for action, rel in plan:
            typer.echo(f"would {action} {target / rel}")
        return

    manifest = {
        "tool": "eva",
        "version": _eva_version(),
        "files": {rel: _sha(data) for rel, data in bundled.items()},
    }
    for action, rel in plan:
        path = target / rel
        if action == "remove":
            path.unlink()
        elif rel == MANIFEST_NAME:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(bundled[rel])
        typer.echo(f"{action} {path}" if action == "remove" else str(path))
