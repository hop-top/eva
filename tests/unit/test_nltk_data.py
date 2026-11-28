"""nltk data setup: explicit fetch only, never implicit; no network here."""
import json
import os
import subprocess
import sys
from pathlib import Path

from core import nltk_data

REPO = Path(__file__).resolve().parents[2]


def fake_downloader(calls):
    def dl(resource, directory):
        calls.append(resource)
        rel = dict((rid, rel) for rel, rid in nltk_data.REQUIRED)[resource]
        (Path(directory) / rel).mkdir(parents=True)
        return True
    return dl


def test_target_dir_priority(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.delenv("NLTK_DATA", raising=False)
    assert nltk_data.target_dir() == tmp_path / "xdg" / "eva" / "nltk_data"
    monkeypatch.setenv("NLTK_DATA", f"{tmp_path / 'a'}{os.pathsep}{tmp_path / 'b'}")
    assert nltk_data.target_dir() == tmp_path / "a"
    assert nltk_data.target_dir(tmp_path / "c") == tmp_path / "c"


def test_missing_and_fetch_with_stub(monkeypatch, tmp_path):
    monkeypatch.delenv("NLTK_DATA", raising=False)
    calls: list[str] = []
    res = nltk_data.fetch(tmp_path, downloader=fake_downloader(calls))
    assert res["ok"] and calls == [rid for _, rid in nltk_data.REQUIRED]
    assert {r["status"] for r in res["resources"]} == {"fetched"}
    assert nltk_data.missing([tmp_path]) == []
    # second run fetches nothing
    calls.clear()
    res = nltk_data.fetch(tmp_path, downloader=fake_downloader(calls))
    assert calls == [] and {r["status"] for r in res["resources"]} == {"present"}


def test_dry_run_does_not_download_or_write(tmp_path):
    calls: list[str] = []
    target = tmp_path / "nd"
    res = nltk_data.fetch(target, dry_run=True, downloader=fake_downloader(calls))
    assert calls == [] and not target.exists()
    assert {r["status"] for r in res["resources"]} == {"would_fetch"}


def test_failed_download_reported(tmp_path):
    res = nltk_data.fetch(tmp_path, downloader=lambda r, d: False)
    assert not res["ok"] and {r["status"] for r in res["resources"]} == {"failed"}


def test_download_exception_reported(tmp_path):
    def boom(r, d):
        raise OSError("offline")
    res = nltk_data.fetch(tmp_path, downloader=boom)
    assert not res["ok"]


def eva(*args, env=None):
    e = {**os.environ, "PYTHONPATH": str(REPO), **(env or {})}
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        capture_output=True, text=True, env=e, cwd=REPO, check=False,
    )


def test_cli_dry_run_json(tmp_path):
    r = eva("data", "fetch", "--dry-run", "--format", "json", "--dir", str(tmp_path / "nd"))
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["dry_run"] is True and out["dir"] == str(tmp_path / "nd")
    assert [x["id"] for x in out["resources"]] == [rid for _, rid in nltk_data.REQUIRED]
    assert not (tmp_path / "nd").exists()


def test_cli_bad_format_exits_2():
    assert eva("data", "fetch", "--dry-run", "--format", "xml").returncode == 2
