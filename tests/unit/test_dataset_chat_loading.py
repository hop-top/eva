import pytest
import yaml

from core.dataset import load_dataset


def _write(tmp_path, doc):
    p = tmp_path / "d.yaml"
    p.write_text(yaml.safe_dump(doc))
    return p


CHAT = {"provider": "openai", "base_url": "http://h/v1", "model": "m", "temperature": 0.0}


def test_yaml_mapping_target(tmp_path):
    ds = load_dataset(_write(tmp_path, {"name": "d", "target": CHAT, "tests": []}))
    assert ds.chat.temperature == 0.0 and ds.chat.base_url == "http://h/v1"


def test_chat_flags_override_dataset_target(tmp_path):
    p = _write(tmp_path, {"name": "d", "target": CHAT, "tests": []})
    ds = load_dataset(p, chat={"model": "other", "base_url": None})
    assert ds.chat.model == "other" and ds.chat.base_url == "http://h/v1"


def test_chat_flags_build_target_for_url_less_dataset(tmp_path):
    p = _write(tmp_path, {"name": "d", "target": "http://old", "tests": []})
    ds = load_dataset(p, chat={"provider": "openai", "model": "m", "base_url": "http://n/v1"})
    assert ds.chat.model == "m" and ds.target == "openai:m@http://n/v1"


def test_url_override_replaces_mapping(tmp_path):
    p = _write(tmp_path, {"name": "d", "target": CHAT, "tests": []})
    ds = load_dataset(p, target="http://x/agent")
    assert ds.chat is None and ds.target == "http://x/agent"


def test_url_and_chat_exclusive(tmp_path):
    p = _write(tmp_path, {"name": "d", "target": CHAT, "tests": []})
    with pytest.raises(ValueError, match="mutually exclusive"):
        load_dataset(p, target="http://x", chat={"model": "m"})


def test_jsonl_with_chat_flags(tmp_path):
    p = tmp_path / "d.jsonl"
    p.write_text('{"id": "a", "input": "hi", "tests": ["assert True"]}\n')
    ds = load_dataset(p, chat={"provider": "openai", "model": "m"})
    assert ds.chat is not None and ds.tests[0].tests == ["assert True"]


def test_jsonl_without_any_target(tmp_path):
    p = tmp_path / "d.jsonl"
    p.write_text('{"id": "a", "input": "hi"}\n')
    with pytest.raises(ValueError):
        load_dataset(p)


def test_case_tests_field_string_and_list(tmp_path):
    p = _write(tmp_path, {"name": "d", "target": "http://x", "tests": [
        {"id": "a", "input": "i", "tests": "assert 1"},
        {"id": "b", "input": "i", "tests": ["assert 1", "assert 2"]},
    ]})
    ds = load_dataset(p)
    assert ds.tests[0].tests == "assert 1" and ds.tests[1].tests == ["assert 1", "assert 2"]
