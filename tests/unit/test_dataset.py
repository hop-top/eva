# tests/unit/test_dataset.py
from pathlib import Path
from core.dataset import load_dataset, Dataset, EvaTestCase
import pytest

FIXTURES = Path("tests/fixtures/datasets")


def test_load_yaml_dataset():
    ds = load_dataset(FIXTURES / "simple.yaml")
    assert ds.name == "refund_suite"
    assert ds.target == "http://localhost:8000/chat"
    assert len(ds.tests) == 2


def test_load_yaml_test_cases():
    ds = load_dataset(FIXTURES / "simple.yaml")
    assert ds.tests[0].id == "test_01"
    assert ds.tests[0].input == "Refund order 123"
    assert ds.tests[0].expected_output is None
    assert ds.tests[1].expected_output == "balance"


def test_load_jsonl_dataset():
    ds = load_dataset(FIXTURES / "simple.jsonl", target="http://localhost:9000/chat")
    assert len(ds.tests) == 2
    assert ds.target == "http://localhost:9000/chat"


def test_load_jsonl_test_cases():
    ds = load_dataset(FIXTURES / "simple.jsonl", target="http://localhost:9000/chat")
    assert ds.tests[0].id == "test_01"
    assert ds.tests[1].expected_output == "balance"


def test_load_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_dataset(Path("nonexistent.yaml"))
