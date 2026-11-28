"""`eva skill show` and `eva skill install` behaviour."""
import hashlib
import json
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pytest
from typer.testing import CliRunner

import cli
from cli.main import app

runner = CliRunner()
BUNDLED = Path(cli.__file__).resolve().parent / "skills" / "eva-cli"
MANIFEST = ".skill-install.json"


def _bundled() -> dict[str, bytes]:
    return {
        p.relative_to(BUNDLED).as_posix(): p.read_bytes()
        for p in sorted(BUNDLED.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts
    }


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _eva_version() -> str:
    try:
        return version("hop-top-eva")
    except PackageNotFoundError:
        return "0.0.0"


def _install(*args):
    return runner.invoke(app, ["skill", "install", *args])


def _tree(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


# --- show ------------------------------------------------------------------


def test_show_prints_bundled_skill_md():
    r = runner.invoke(app, ["skill", "show"])
    assert r.exit_code == 0, r.output
    assert r.stdout == (BUNDLED / "SKILL.md").read_text()


def test_show_reference_by_name():
    r = runner.invoke(app, ["skill", "show", "rest-api"])
    assert r.exit_code == 0, r.output
    assert r.stdout == (BUNDLED / "references" / "rest-api.md").read_text()


def test_show_every_reference_name_works():
    for ref in (BUNDLED / "references").glob("*.md"):
        r = runner.invoke(app, ["skill", "show", ref.stem])
        assert r.exit_code == 0, ref
        assert r.stdout == ref.read_text()


@pytest.mark.parametrize("name", ["nope", "rest-api.md", "../SKILL", "references/rest-api", ""])
def test_show_unknown_name_is_usage_error_listing_valid_names(name):
    r = runner.invoke(app, ["skill", "show", name])
    assert r.exit_code == 2
    for ref in (BUNDLED / "references").glob("*.md"):
        assert ref.stem in r.output


def test_show_ignores_installed_copy(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert _install().exit_code == 0
    installed = tmp_path / ".claude" / "skills" / "eva-cli" / "SKILL.md"
    installed.write_text("tampered")
    r = runner.invoke(app, ["skill", "show"])
    assert r.exit_code == 0
    assert r.stdout == (BUNDLED / "SKILL.md").read_text()


def test_show_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    runner.invoke(app, ["skill", "show"])
    assert list(tmp_path.iterdir()) == []


# --- install: fresh targets -------------------------------------------------


def test_install_into_missing_dir_writes_tree_and_manifest(tmp_path):
    target = tmp_path / "out" / "eva-cli"
    r = _install("--dir", str(target))
    assert r.exit_code == 0, r.output
    files = _tree(target)
    manifest = json.loads(files.pop(MANIFEST))
    assert files == _bundled()
    assert manifest == {
        "tool": "eva",
        "version": _eva_version(),
        "files": {k: _sha(v) for k, v in _bundled().items()},
    }


def test_install_prints_every_written_path(tmp_path):
    target = tmp_path / "eva-cli"
    r = _install("--dir", str(target))
    for rel in [*_bundled(), MANIFEST]:
        assert str(target / rel) in r.stdout


def test_install_into_empty_existing_dir(tmp_path):
    target = tmp_path / "eva-cli"
    target.mkdir()
    assert _install("--dir", str(target)).exit_code == 0
    assert (target / "SKILL.md").is_file()


def test_install_default_dir_is_claude_skills_under_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    r = _install()
    assert r.exit_code == 0, r.output
    assert (tmp_path / ".claude" / "skills" / "eva-cli" / "SKILL.md").is_file()
    assert (tmp_path / ".claude" / "skills" / "eva-cli" / MANIFEST).is_file()


def test_manifest_version_matches_eva_version(tmp_path):
    target = tmp_path / "t"
    _install("--dir", str(target))
    v = runner.invoke(app, ["version"]).stdout.strip()
    assert json.loads((target / MANIFEST).read_text())["version"] == v


# --- install: managed targets ----------------------------------------------


def test_reinstall_over_untouched_copy_succeeds(tmp_path):
    target = tmp_path / "t"
    _install("--dir", str(target))
    r = _install("--dir", str(target))
    assert r.exit_code == 0, r.output
    assert _tree(target).keys() == {*_bundled(), MANIFEST}


def test_reinstall_removes_manifest_listed_files_no_longer_bundled(tmp_path):
    target = tmp_path / "t"
    _install("--dir", str(target))
    old = target / "references" / "retired.md"
    old.write_bytes(b"old")
    manifest = json.loads((target / MANIFEST).read_text())
    manifest["files"]["references/retired.md"] = _sha(b"old")
    (target / MANIFEST).write_text(json.dumps(manifest))
    r = _install("--dir", str(target))
    assert r.exit_code == 0, r.output
    assert not old.exists()
    assert "references/retired.md" in r.stdout


def test_reinstall_rewrites_manifest_version(tmp_path):
    target = tmp_path / "t"
    _install("--dir", str(target))
    manifest = json.loads((target / MANIFEST).read_text())
    manifest["version"] = "0.0.1"
    (target / MANIFEST).write_text(json.dumps(manifest))
    assert _install("--dir", str(target)).exit_code == 0
    assert json.loads((target / MANIFEST).read_text())["version"] == _eva_version()


# --- install: refusals ------------------------------------------------------


def test_refuses_modified_file_names_it_and_changes_nothing(tmp_path):
    target = tmp_path / "t"
    _install("--dir", str(target))
    (target / "SKILL.md").write_text("local edit")
    before = _tree(target)
    r = _install("--dir", str(target))
    assert r.exit_code != 0
    assert "SKILL.md" in r.output
    assert _tree(target) == before


def test_refuses_extra_file_the_manifest_does_not_list(tmp_path):
    target = tmp_path / "t"
    _install("--dir", str(target))
    (target / "notes.txt").write_text("mine")
    r = _install("--dir", str(target))
    assert r.exit_code != 0
    assert "notes.txt" in r.output
    assert (target / "notes.txt").read_text() == "mine"


def test_refuses_missing_listed_file(tmp_path):
    target = tmp_path / "t"
    _install("--dir", str(target))
    (target / "SKILL.md").unlink()
    r = _install("--dir", str(target))
    assert r.exit_code != 0
    assert "SKILL.md" in r.output


def test_refuses_non_empty_dir_without_manifest(tmp_path):
    target = tmp_path / "t"
    target.mkdir()
    (target / "SKILL.md").write_text("someone else's skill")
    r = _install("--dir", str(target))
    assert r.exit_code != 0
    assert "SKILL.md" in r.output
    assert (target / "SKILL.md").read_text() == "someone else's skill"
    assert not (target / MANIFEST).exists()


def test_refuses_manifest_from_another_tool_or_garbage(tmp_path):
    target = tmp_path / "t"
    target.mkdir()
    (target / "x.md").write_text("x")
    (target / MANIFEST).write_text(json.dumps({"tool": "ben", "version": "1", "files": {}}))
    assert _install("--dir", str(target)).exit_code != 0
    (target / MANIFEST).write_text("not json")
    assert _install("--dir", str(target)).exit_code != 0


def test_refuses_manifest_paths_that_escape_the_target(tmp_path):
    target = tmp_path / "t"
    target.mkdir()
    victim = tmp_path / "victim.txt"
    victim.write_text("keep")
    (target / MANIFEST).write_text(
        json.dumps({"tool": "eva", "version": "1", "files": {"../victim.txt": _sha(b"keep")}})
    )
    r = _install("--dir", str(target))
    assert r.exit_code != 0
    assert victim.read_text() == "keep"


def test_refuses_when_target_is_a_file(tmp_path):
    target = tmp_path / "t"
    target.write_text("x")
    assert _install("--dir", str(target)).exit_code != 0
    assert target.read_text() == "x"


# --- install: --force -------------------------------------------------------


def test_force_overwrites_modified_copy(tmp_path):
    target = tmp_path / "t"
    _install("--dir", str(target))
    (target / "SKILL.md").write_text("local edit")
    r = _install("--dir", str(target), "--force")
    assert r.exit_code == 0, r.output
    assert (target / "SKILL.md").read_bytes() == _bundled()["SKILL.md"]


def test_force_installs_over_foreign_dir_and_keeps_unrelated_files(tmp_path):
    target = tmp_path / "t"
    target.mkdir()
    (target / "SKILL.md").write_text("foreign")
    (target / "mine.txt").write_text("keep")
    r = _install("--dir", str(target), "--force")
    assert r.exit_code == 0, r.output
    assert (target / "SKILL.md").read_bytes() == _bundled()["SKILL.md"]
    assert (target / "mine.txt").read_text() == "keep"
    assert (target / MANIFEST).is_file()


# --- install: --dry-run -----------------------------------------------------


def test_dry_run_into_fresh_target_writes_nothing_and_lists_writes(tmp_path):
    target = tmp_path / "t"
    r = _install("--dir", str(target), "--dry-run")
    assert r.exit_code == 0, r.output
    assert not target.exists()
    assert "write" in r.stdout and "SKILL.md" in r.stdout


def test_dry_run_reports_replace_and_remove_and_writes_nothing(tmp_path):
    target = tmp_path / "t"
    _install("--dir", str(target))
    (target / "references" / "retired.md").write_bytes(b"old")
    manifest = json.loads((target / MANIFEST).read_text())
    manifest["files"]["references/retired.md"] = _sha(b"old")
    (target / MANIFEST).write_text(json.dumps(manifest))
    before = _tree(target)
    r = _install("--dir", str(target), "--dry-run")
    assert r.exit_code == 0, r.output
    assert "replace" in r.stdout
    assert "remove" in r.stdout and "references/retired.md" in r.stdout
    assert _tree(target) == before


def test_dry_run_still_refuses_modified_copy(tmp_path):
    target = tmp_path / "t"
    _install("--dir", str(target))
    (target / "SKILL.md").write_text("local edit")
    r = _install("--dir", str(target), "--dry-run")
    assert r.exit_code != 0
    assert "SKILL.md" in r.output
    assert (target / "SKILL.md").read_text() == "local edit"
