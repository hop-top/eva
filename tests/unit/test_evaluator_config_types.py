"""Wrong-typed or out-of-range evaluator config fails at build, naming the key.

One table, four paths: the builder, a dataset run, contract load and the
gateway's inline evaluators all report the same ``EvaluatorConfigError``.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from core.contract import ContractValidationError, load_contract
from core.dataset import Dataset
from core.evaluators.builtin import BUILTIN_EVALUATOR_FACTORIES
from core.evaluators.errors import EvaluatorConfigError, build_evaluator
from core.plugins import make_manager
from core.runner import Runner

# (evaluator, bad config, key the message must name, text of the bad value)
BAD = [
    ("contains", {"substring": 5}, "substring", "5"),
    ("contains", {"substring": None}, "substring", "None"),
    ("contains", {"substring": "a", "case_sensitive": "yes"}, "case_sensitive", "yes"),
    ("contains", {"substring": "a", "field": 3}, "field", "3"),
    ("regex", {"pattern": 5}, "pattern", "5"),
    ("regex", {"pattern": "("}, "pattern", "'('"),
    ("regex", {"pattern": "a", "field": ["x"]}, "field", "x"),
    ("last_paragraph_regex", {"pattern": ["a"]}, "pattern", "a"),
    ("last_paragraph_regex", {"pattern": "(["}, "pattern", "(["),
    ("last_paragraph_regex", {"pattern": "a", "case_sensitive": 1}, "case_sensitive", "1"),
    ("json_schema_valid", {"schema": "string"}, "schema", "string"),
    ("json_schema_valid", {"schema": ["a"]}, "schema", "a"),
    ("json_schema_valid", {"schema": {"type": "strange"}}, "schema", "strange"),
    ("word_count", {"max": "100"}, "max", "100"),
    ("word_count", {"min": "5"}, "min", "5"),
    ("word_count", {"max": 1.5}, "max", "1.5"),
    ("word_count", {"max": True}, "max", "True"),
    ("sentence_paragraph_count", {"min": "2"}, "min", "2"),
    ("sentence_paragraph_count", {"max": [3]}, "max", "3"),
    ("code_block_runs", {"unsupported_action": "explode"}, "unsupported_action", "explode"),
    ("code_block_runs", {"unsupported_action": 1}, "unsupported_action", "1"),
    ("code_block_runs", {"require_code_block": "yes"}, "require_code_block", "yes"),
    ("tool_call_match", {"match": "fuzzy"}, "match", "fuzzy"),
    ("tool_call_match", {"match": 3}, "match", "3"),
    ("tool_call_match", {"case_sensitive": "no"}, "case_sensitive", "no"),
    ("tool_call_match", {"normalize_whitespace": 0}, "normalize_whitespace", "0"),
    ("citation", {"allowed_sources": 5}, "allowed_sources", "5"),
    ("citation", {"allowed_sources": "abc"}, "allowed_sources", "abc"),
    ("citation", {"allowed_sources": [1]}, "allowed_sources", "1"),
    ("citation", {"require_citation": "true"}, "require_citation", "true"),
    ("forbidden_phrases", {"banlist": "delve"}, "banlist", "delve"),
    ("forbidden_phrases", {"banlist": [1, 2]}, "banlist", "1"),
    ("forbidden_phrases", {"banlist": ["a"], "whole_word": "x"}, "whole_word", "x"),
    ("forbidden_phrases", {"banlist": ["a"], "case_sensitive": "x"}, "case_sensitive", "x"),
    ("markdown_structure", {"required_h2": "Intro"}, "required_h2", "Intro"),
    ("markdown_structure", {"required_code_langs": [1]}, "required_code_langs", "1"),
    ("markdown_structure", {"disallow_broken_local_links": "x"}, "disallow_broken_local_links", "x"),
    ("mood", {"expected": 5}, "expected", "5"),
    ("language", {"expected": ["en"]}, "expected", "en"),
    ("equals", {"field": 3, "expected": 1}, "field", "3"),
    ("equals", {"field": "a", "expected": 1, "step": 3}, "step", "3"),
    ("json_path", {"path": 5}, "path", "5"),
    ("status_code", {"expected": "0"}, "expected", "0"),
    ("status_code", {"expected_in": 5}, "expected_in", "5"),
    ("status_code", {"expected_in": ["a"]}, "expected_in", "a"),
    ("exit_code", {"expected": 0, "step": 4}, "step", "4"),
    ("code_test_passes", {"test_code": 5}, "test_code", "5"),
    ("code_test_passes", {"timeout": "10"}, "timeout", "10"),
    ("code_test_passes", {"timeout": 0}, "timeout", "0"),
    ("code_tests", {"timeout": "10"}, "timeout", "10"),
    ("code_tests", {"test_code": 5}, "test_code", "5"),
    ("code_tests", {"memory_mb": "512"}, "memory_mb", "512"),
    ("code_tests", {"max_file_mb": 1.5}, "max_file_mb", "1.5"),
    ("code_tests", {"partial": "yes"}, "partial", "yes"),
    ("code_tests", {"require_isolation": "yes"}, "require_isolation", "yes"),
    ("ifeval_check", {"instruction_id_list": "a:b"}, "instruction_id_list", "a:b"),
    ("ifeval_check", {"instruction_id_list": [1]}, "instruction_id_list", "1"),
    ("ifeval_check", {"kwargs": {"a": 1}}, "kwargs", "'a'"),
    ("prose_assertion", {"assertion": 5}, "assertion", "5"),
    ("prose_assertion", {"assertion": "x", "assertion_mode": 5}, "assertion_mode", "5"),
]

# Existing value checks keep naming the key too.
ALREADY_NAMED = [
    ("refusal", {"mode": "sideways"}, "mode", "sideways"),
    ("refusal", {"mode": ["forbid"]}, "mode", "forbid"),
    ("sentence_paragraph_count", {"mode": "word"}, "mode", "word"),
    ("json_path", {"path": "$.a", "comparator": "approx"}, "comparator", "approx"),
    ("ifeval_check", {"pass_on": "sloppy"}, "pass_on", "sloppy"),
]

CASES = BAD + ALREADY_NAMED
IDS = [f"{n}-{k}-{i}" for i, (n, _, k, _) in enumerate(CASES)]


def _msg_ok(msg: str, name: str, key: str, shown: str) -> None:
    assert msg.startswith(f"evaluator {name!r}: "), msg
    assert key in msg.split(": ", 1)[1], msg
    assert shown in msg, msg


@pytest.mark.parametrize("name,cfg,key,shown", CASES, ids=IDS)
def test_build_evaluator(name, cfg, key, shown):
    with pytest.raises(EvaluatorConfigError) as exc:
        build_evaluator(name, BUILTIN_EVALUATOR_FACTORIES[name], cfg, None)
    assert exc.value.evaluator == name
    _msg_ok(str(exc.value), name, key, shown)


@pytest.mark.parametrize("name,cfg,key,shown", CASES, ids=IDS)
@pytest.mark.asyncio
async def test_dataset_run(name, cfg, key, shown):
    calls: list[str] = []

    async def call(prompt, target):
        calls.append(prompt)
        return "hi"

    ds = Dataset(
        name="d", target="http://x", evaluators=[{"name": name, **cfg}],
        tests=[{"id": "t", "input": "hi"}],
    )
    with pytest.raises(EvaluatorConfigError) as exc:
        await Runner(pm=make_manager(), call_agent=call).execute(ds)
    assert calls == []
    _msg_ok(str(exc.value), name, key, shown)


# ``mode`` is the pass mode in a contract entry, so refusal/sentence mode
# cases belong to the dataset and gateway paths only.
CONTRACT_CASES = [c for c in CASES if c[2] != "mode"]


@pytest.mark.parametrize("name,cfg,key,shown", CONTRACT_CASES)
def test_contract_load(tmp_path, name, cfg, key, shown):
    f = tmp_path / "c.yaml"
    f.write_text(yaml.dump({
        "name": "c", "provider": "noop",
        "evaluators": [{"name": name, **cfg}],
    }))
    with pytest.raises(ContractValidationError) as exc:
        load_contract(f)
    _msg_ok(str(exc.value), name, key, shown)


@pytest.mark.asyncio
@pytest.mark.parametrize("name,cfg,key,shown", CASES, ids=IDS)
async def test_proxy_inline(name, cfg, key, shown):
    from server.app import create_app

    app = create_app()
    with patch("server.gateway.routes.forward_request", new_callable=AsyncMock) as fwd:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.post("/v1/proxy", json={
                "target": "http://agent.invalid/x", "body": {"input": "hi"},
                "evaluators": [{"name": name, "config": cfg}],
            })
        fwd.assert_not_called()
    assert r.status_code == 422, r.text
    _msg_ok(r.json()["detail"], name, key, shown)


# Valid configs of the same keys keep building.
GOOD = [
    ("contains", {"substring": "a", "case_sensitive": False, "field": "x"}),
    ("regex", {"pattern": "a+", "field": "x"}),
    ("last_paragraph_regex", {"pattern": "a", "case_sensitive": False}),
    ("json_schema_valid", {"schema": {"type": "object", "required": ["a"]}}),
    ("json_schema_valid", {}),
    ("word_count", {"max": 10, "min": 1}),
    ("word_count", {"max": None}),
    ("sentence_paragraph_count", {"mode": "paragraph", "min": 1, "max": 3}),
    ("code_block_runs", {"unsupported_action": "fail", "require_code_block": True}),
    ("tool_call_match", {"match": "ordered", "case_sensitive": False,
                         "normalize_whitespace": True}),
    ("citation", {"allowed_sources": ["a", "b"], "require_citation": True}),
    ("forbidden_phrases", {"banlist": ["x"], "whole_word": False, "case_sensitive": True}),
    ("markdown_structure", {"required_h2": ["A"], "required_code_langs": ["py"],
                            "disallow_broken_local_links": True}),
    ("equals", {"field": "a", "expected": None, "step": "s"}),
    ("status_code", {"expected_in": [0, 1], "step": "s"}),
    ("code_test_passes", {"test_code": "x=1", "timeout": 2.5}),
    ("code_tests", {"timeout": 5, "memory_mb": 256, "max_file_mb": 8, "partial": True}),
    ("ifeval_check", {"instruction_id_list": ["a:b"], "kwargs": [{"n": 1}, None]}),
    ("prose_assertion", {"assertion": "starts with 'feat/'"}),
]


@pytest.mark.parametrize("name,cfg", GOOD)
def test_valid_config_builds(name, cfg):
    assert build_evaluator(name, BUILTIN_EVALUATOR_FACTORIES[name], cfg, None) is not None
