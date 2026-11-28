"""Build the wheel, install it in a fresh venv, run `eva skill` from it.

Not editable: an editable install hides files the wheel would miss. Runs
outside the repo so the checkout cannot shadow the installed package. Needs
`uv` (to build and create the venv) and builds with hatchling from cache or network; skipped when
`uv` is absent. Third-party dependencies come from the test environment: a
.pth line appends its site-packages after the venv's own, so the installed
wheel wins for `cli` and the venv install itself needs no index.
"""
import json
import shutil
import subprocess
import sys
import sysconfig
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed"),
]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("dist")
    r = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(out), str(REPO)],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    wheels = list(out.glob("*.whl"))
    assert len(wheels) == 1
    return wheels[0]


@pytest.fixture(scope="module")
def venv_eva(built, tmp_path_factory):
    env_dir = tmp_path_factory.mktemp("venv")
    made = subprocess.run(
        ["uv", "venv", "--python", sys.executable, str(env_dir)],
        capture_output=True,
        text=True,
    )
    assert made.returncode == 0, made.stdout + made.stderr
    py = env_dir / "bin" / "python"
    site = Path(
        subprocess.run(
            [str(py), "-c", "import sysconfig;print(sysconfig.get_paths()['purelib'])"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )
    (site / "zz_test_env.pth").write_text(sysconfig.get_paths()["purelib"] + "\n")
    r = subprocess.run(
        ["uv", "pip", "install", "--python", str(py), "--no-deps", "--no-index", str(built)],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    return env_dir


def test_wheel_lists_skill_tree(built):
    names = zipfile.ZipFile(built).namelist()
    assert "cli/skills/eva-cli/SKILL.md" in names
    for ref in (REPO / "cli" / "skills" / "eva-cli" / "references").glob("*.md"):
        assert f"cli/skills/eva-cli/references/{ref.name}" in names


def test_installed_wheel_serves_and_installs_skill(venv_eva, tmp_path):
    eva = venv_eva / "bin" / "eva"
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    where = subprocess.run(
        [str(venv_eva / "bin" / "python"), "-c", "import cli; print(cli.__file__)"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    assert str(venv_eva) in where.stdout, where.stdout + where.stderr

    shown = subprocess.run(
        [str(eva), "skill", "show"], capture_output=True, text=True, cwd=cwd
    )
    assert shown.returncode == 0, shown.stderr
    assert shown.stdout == (REPO / "cli/skills/eva-cli/SKILL.md").read_text()

    ref = subprocess.run(
        [str(eva), "skill", "show", "rest-api"], capture_output=True, text=True, cwd=cwd
    )
    assert ref.returncode == 0, ref.stderr

    target = tmp_path / "eva-cli"
    inst = subprocess.run(
        [str(eva), "skill", "install", "--dir", str(target)],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    assert inst.returncode == 0, inst.stderr
    ver = subprocess.run(
        [str(eva), "version"], capture_output=True, text=True, cwd=cwd
    ).stdout.strip()
    manifest = json.loads((target / ".skill-install.json").read_text())
    assert manifest["version"] == ver != ""
    assert (target / "SKILL.md").read_text() == shown.stdout
    assert (target / "references" / "rest-api.md").is_file()
