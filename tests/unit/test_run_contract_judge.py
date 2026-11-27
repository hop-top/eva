"""Judge evaluators in `eva run --contract --input --prompt`.

`litellm.acompletion` is always mocked; no request leaves the process.
"""
from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from cli.run_contract import evaluate_contract, run_contract_cli
from core.evaluators.builtin import BUILTIN_EVALUATOR_FACTORIES
from core.llm import LiteLLMAdapter


def _resp(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=None,
        model="m",
    )


def _contract(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "c.yaml"
    p.write_text("name: judged\nprovider: noop\nevaluators:\n" + dedent(body))
    return p


def _adapter():
    return LiteLLMAdapter("openai/judge-model")


def _sent(mock) -> str:
    return json.dumps([c.kwargs["messages"] for c in mock.await_args_list])


def test_prompt_and_response_reach_judge_call(tmp_path):
    c = _contract(tmp_path, "  - name: relevance\n    mode: threshold\n    min_score: 0.5\n")
    with patch("litellm.acompletion", new_callable=AsyncMock) as m:
        m.return_value = _resp("0.9\nfits")
        r = evaluate_contract(
            c, "RESPONSE-BODY-7", llm_adapter=_adapter(), prompt="PROMPT-TEXT-3"
        )
    m.assert_awaited_once()
    sent = _sent(m)
    assert "PROMPT-TEXT-3" in sent and "RESPONSE-BODY-7" in sent
    assert m.await_args.kwargs["model"] == "openai/judge-model"
    assert [o.name for o in r.outcomes] == ["relevance"]
    assert r.outcomes[0].score == 0.9 and r.outcomes[0].passed
    assert r.skipped_judge == [] and r.passed


def test_judge_verdict_counts_toward_pass(tmp_path):
    c = _contract(tmp_path, "  - name: relevance\n    mode: threshold\n    min_score: 0.5\n")
    with patch("litellm.acompletion", new_callable=AsyncMock) as m:
        m.return_value = _resp("0.1\nbad")
        r = evaluate_contract(c, "x", llm_adapter=_adapter(), prompt="p")
    assert r.passed is False
    assert r.outcomes[0].passed is False and r.outcomes[0].reason == "bad"


def test_outcome_order_follows_contract(tmp_path):
    c = _contract(
        tmp_path,
        """
          - name: contains
            substring: a
          - name: relevance
            mode: warn
          - name: contains
            substring: zzz
            mode: warn
        """,
    )
    with patch("litellm.acompletion", new_callable=AsyncMock) as m:
        m.return_value = _resp("1.0")
        r = evaluate_contract(c, "a", llm_adapter=_adapter(), prompt="p")
    assert [o.name for o in r.outcomes] == ["contains", "relevance", "contains"]


def test_judge_without_prompt_skips_pointing_at_flags(tmp_path):
    c = _contract(tmp_path, "  - name: relevance\n  - name: contains\n    substring: a\n")
    with patch("litellm.acompletion", new_callable=AsyncMock) as m:
        r = evaluate_contract(c, "a", llm_adapter=_adapter())
    m.assert_not_awaited()
    assert [o.name for o in r.outcomes] == ["contains"]
    (entry,) = r.skipped_judge
    assert entry.startswith("relevance: ")
    assert "--prompt" in entry and "--prompt-file" in entry


def test_no_judge_skips_even_with_prompt(tmp_path):
    c = _contract(tmp_path, "  - name: relevance\n")
    r = evaluate_contract(c, "a", prompt="p")
    assert r.skipped_judge == ["relevance: no judge model configured"]
    assert r.outcomes == []


@pytest.mark.parametrize(
    "name,extra,needs",
    [
        ("tool_use", "", "tool events"),
        ("tool_correctness", "", "tool events"),
        ("argument_correctness", "", "tool events"),
        ("step_efficiency", "", "tool events"),
        ("plan_adherence", "", "planned steps"),
        ("rag:contextual_relevancy", "", "retrieval context"),
        ("rag:contextual_precision", "", "retrieval context"),
        ("rag:contextual_recall", "", "retrieval context"),
        ("ragas", "", "retrieval context"),
        ("content:goal_accuracy", "", "expected output"),
    ],
)
def test_judges_needing_other_inputs_skip_precisely(tmp_path, name, extra, needs):
    c = _contract(tmp_path, f"  - name: {name}\n")
    with patch("litellm.acompletion", new_callable=AsyncMock) as m:
        r = evaluate_contract(c, "a", llm_adapter=_adapter(), prompt="p")
    m.assert_not_awaited()
    assert r.outcomes == []
    (entry,) = r.skipped_judge
    assert entry.startswith(f"{name}: ") and needs in entry
    assert "--prompt" not in entry  # more flags would not help


def test_goal_accuracy_runs_when_contract_gives_expected_output(tmp_path):
    c = _contract(tmp_path, "  - name: content:goal_accuracy\n    expected_output: EXPECTED-9\n")
    with patch("litellm.acompletion", new_callable=AsyncMock) as m:
        m.return_value = _resp("1.0")
        r = evaluate_contract(c, "a", llm_adapter=_adapter(), prompt="p")
    assert "EXPECTED-9" in _sent(m)
    assert [o.name for o in r.outcomes] == ["content:goal_accuracy"]


def test_failing_judge_call_is_a_failed_outcome_not_a_crash(tmp_path):
    c = _contract(
        tmp_path,
        "  - name: relevance\n  - name: contains\n    substring: a\n",
    )
    with patch("litellm.acompletion", new_callable=AsyncMock) as m:
        m.side_effect = ConnectionError("endpoint unreachable")
        r = evaluate_contract(c, "a", llm_adapter=_adapter(), prompt="p")
    assert r.passed is False
    rel, cont = r.outcomes
    assert rel.name == "relevance" and rel.score == 0.0 and not rel.passed
    assert rel.reason.startswith("judge error") and "unreachable" in rel.reason
    assert cont.passed


def test_failing_judge_in_warn_mode_does_not_fail_run(tmp_path):
    c = _contract(tmp_path, "  - name: relevance\n    mode: warn\n")
    with patch("litellm.acompletion", new_callable=AsyncMock) as m:
        m.side_effect = TimeoutError("slow")
        r = evaluate_contract(c, "a", llm_adapter=_adapter(), prompt="p")
    assert r.passed is True and r.outcomes[0].reason.startswith("judge error")


def test_malformed_judge_output_scored_like_dataset_mode(tmp_path):
    c = _contract(tmp_path, "  - name: relevance\n    mode: warn\n")
    with patch("litellm.acompletion", new_callable=AsyncMock) as m:
        m.return_value = _resp("no number here")
        r = evaluate_contract(c, "a", llm_adapter=_adapter(), prompt="p")
    assert r.outcomes[0].score == 0.5
    assert r.outcomes[0].reason == "no number here"


def test_every_judge_factory_is_classified():
    from cli.run_contract import JUDGE_PROMPT_ONLY, JUDGE_NEEDS

    judges = set()
    for name, factory in BUILTIN_EVALUATOR_FACTORIES.items():
        try:
            factory({"criteria": "c"}, None)
        except ValueError as e:
            if "llm_adapter" in str(e):
                judges.add(name)
    assert judges == set(JUDGE_PROMPT_ONLY) | set(JUDGE_NEEDS)
    assert not set(JUDGE_PROMPT_ONLY) & set(JUDGE_NEEDS)


def test_cli_entry_passes_prompt_to_judge(tmp_path, monkeypatch, capsys):
    c = _contract(tmp_path, "  - name: relevance\n    mode: threshold\n    min_score: 0.5\n")
    i = tmp_path / "in.txt"
    i.write_text("RESP-11")
    monkeypatch.setenv("EVA_JUDGE_MODEL", "openai/judge-model")
    monkeypatch.chdir(tmp_path)
    out, err = __import__("io").StringIO(), __import__("io").StringIO()
    with patch("litellm.acompletion", new_callable=AsyncMock) as m:
        m.return_value = _resp("0.8")
        code = run_contract_cli(c, str(i), "json", False, stdout=out, stderr=err,
                                prompt="PROMPT-12")
    assert code == 0, err.getvalue()
    assert "PROMPT-12" in _sent(m) and "RESP-11" in _sent(m)
    assert json.loads(out.getvalue())["skipped_judge"] == []


def test_cli_entry_prompt_file_missing_is_bad_input(tmp_path, monkeypatch):
    c = _contract(tmp_path, "  - name: contains\n    substring: a\n")
    i = tmp_path / "in.txt"
    i.write_text("a")
    monkeypatch.chdir(tmp_path)
    import io
    err = io.StringIO()
    code = run_contract_cli(c, str(i), "json", False, stdout=io.StringIO(), stderr=err,
                            prompt_file=str(tmp_path / "nope.txt"))
    assert code == 2 and "nope.txt" in err.getvalue()
