"""Plugins must depend on the core distribution by its real name."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[2]
ROOT_PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
PLUGIN_FILES = sorted(ROOT.glob("plugins/*/pyproject.toml"))


def _requirements(path: Path) -> list[Requirement]:
    project = tomllib.loads(path.read_text())["project"]
    return [Requirement(dep) for dep in project.get("dependencies", [])]


def test_plugins_discovered() -> None:
    assert PLUGIN_FILES, "no plugin pyproject.toml files found"


@pytest.mark.parametrize("path", PLUGIN_FILES, ids=lambda p: p.parent.name)
def test_plugin_does_not_depend_on_unrelated_eva_dist(path: Path) -> None:
    names = {canonicalize_name(r.name) for r in _requirements(path)}
    assert "eva" not in names


@pytest.mark.parametrize("path", PLUGIN_FILES, ids=lambda p: p.parent.name)
def test_plugin_depends_on_root_distribution(path: Path) -> None:
    root_name = canonicalize_name(ROOT_PROJECT["name"])
    names = {canonicalize_name(r.name) for r in _requirements(path)}
    assert root_name in names


@pytest.mark.parametrize("path", PLUGIN_FILES, ids=lambda p: p.parent.name)
def test_plugin_specifier_admits_root_version(path: Path) -> None:
    root_name = canonicalize_name(ROOT_PROJECT["name"])
    version = Version(ROOT_PROJECT["version"])
    reqs = [r for r in _requirements(path) if canonicalize_name(r.name) == root_name]
    assert reqs, "no dependency on root distribution"
    for req in reqs:
        assert req.specifier.contains(version, prereleases=True), (
            f"{req} excludes current version {version}"
        )


# Install instructions that users and the published action follow. Planning
# and research notes under docs/ subdirectories are historical and excluded.
INSTALL_DOC_FILES = sorted(
    [ROOT / "action.yml", ROOT / "README.md", *ROOT.glob("docs/*.md")]
)
_STALE_INSTALL = re.compile(
    r"(?:pip install|uv add|twine yank)"  # also matches `uv pip install`
    r"(?:\s+--?[\w-]+)*"  # flags such as --system
    r"\s+[\"']?(eva(?:-core)?)(?=[\[=\s\"'\\]|$)",
    re.MULTILINE,
)


def test_install_doc_files_discovered() -> None:
    assert (ROOT / "action.yml") in INSTALL_DOC_FILES
    assert len(INSTALL_DOC_FILES) > 2


@pytest.mark.parametrize(
    "path", INSTALL_DOC_FILES, ids=lambda p: str(p.relative_to(ROOT))
)
def test_install_instructions_name_root_distribution(path: Path) -> None:
    stale = [
        f"{path.relative_to(ROOT)}:{path.read_text()[: m.start()].count(chr(10)) + 1}"
        for m in _STALE_INSTALL.finditer(path.read_text())
    ]
    assert not stale, (
        f"install lines name a distribution other than "
        f"{ROOT_PROJECT['name']!r}: {stale}"
    )
