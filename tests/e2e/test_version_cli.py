"""End-to-end: `eva --version` and `eva version` agree and exit 0."""
import subprocess
import sys


def run_eva(*args):
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args], capture_output=True, text=True
    )


def test_version_flag_matches_version_command():
    flag = run_eva("--version")
    cmd = run_eva("version")
    assert flag.returncode == 0, flag.stderr
    assert cmd.returncode == 0, cmd.stderr
    assert flag.stdout.strip() == cmd.stdout.strip() != ""
