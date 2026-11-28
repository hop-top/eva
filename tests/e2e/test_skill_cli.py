"""End-to-end: `eva skill` through the real entry point."""
import json
import subprocess
import sys


def run_eva(*args, home=None, cwd=None):
    env = None
    if home is not None:
        import os

        env = {**os.environ, "HOME": str(home)}
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
    )


def test_skill_show_prints_skill_md():
    r = run_eva("skill", "show")
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("---\nname: eva-cli\n")


def test_skill_show_unknown_reference_exits_2():
    r = run_eva("skill", "show", "nope")
    assert r.returncode == 2
    assert "rest-api" in r.stderr + r.stdout


def test_skill_install_dir_yields_tree_with_version(tmp_path):
    target = tmp_path / "eva-cli"
    r = run_eva("skill", "install", "--dir", str(target))
    assert r.returncode == 0, r.stderr
    assert (target / "SKILL.md").is_file()
    manifest = json.loads((target / ".skill-install.json").read_text())
    assert manifest["tool"] == "eva"
    assert manifest["version"] == run_eva("version").stdout.strip()


def test_skill_install_does_not_touch_home_unless_asked(tmp_path):
    run_eva("skill", "show", home=tmp_path)
    assert list(tmp_path.iterdir()) == []
