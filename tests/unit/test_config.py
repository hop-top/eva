# tests/unit/test_config.py
import pytest
from pathlib import Path
from core.config import EvaConfig, find_and_load_config


def test_defaults():
    cfg = EvaConfig()
    assert cfg.version == "1"
    assert cfg.project == "eva"
    assert cfg.storage == "sqlite"
    assert cfg.otel == "noop"
    assert cfg.concurrency == "semaphore"
    assert cfg.max_workers == 4
    assert cfg.min_score == 0.0


def test_find_and_load_config_returns_defaults_when_no_file(tmp_path):
    cfg = find_and_load_config(start=tmp_path)
    assert isinstance(cfg, EvaConfig)
    assert cfg.project == "eva"


def test_find_and_load_config_reads_file(tmp_path):
    config_file = tmp_path / "eva.yaml"
    config_file.write_text("project: myapp\nmax_workers: 8\n")
    cfg = find_and_load_config(start=tmp_path)
    assert cfg.project == "myapp"
    assert cfg.max_workers == 8


def test_find_and_load_config_walks_up(tmp_path):
    config_file = tmp_path / "eva.yaml"
    config_file.write_text("project: parentapp\n")
    subdir = tmp_path / "a" / "b"
    subdir.mkdir(parents=True)
    cfg = find_and_load_config(start=subdir)
    assert cfg.project == "parentapp"


def test_empty_yaml_returns_defaults(tmp_path):
    config_file = tmp_path / "eva.yaml"
    config_file.write_text("")
    cfg = find_and_load_config(start=tmp_path)
    assert cfg.project == "eva"
