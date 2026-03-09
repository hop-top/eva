# tests/e2e/test_init.py
import subprocess
import sys
from pathlib import Path


def test_eva_init_creates_structure(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "cli.main", "init"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert (tmp_path / "evals").is_dir()
    assert (tmp_path / "eva_plugins.py").exists()
    assert (tmp_path / ".env").exists()


def test_eva_init_output_mentions_created(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "cli.main", "init"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert "evals" in result.stdout
    assert "eva_plugins.py" in result.stdout


def test_eva_init_idempotent(tmp_path):
    for _ in range(2):
        result = subprocess.run(
            [sys.executable, "-m", "cli.main", "init"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
