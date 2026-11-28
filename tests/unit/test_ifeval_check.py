"""ifeval_check: IFEval/IFBench verifiers on a reply (strict/loose, prompt-level).

Verifier tests need the ``ifeval`` extra and the nltk data; they skip with a
reason when either is absent. Nothing here touches the network.
"""
import importlib.util
import sys

import pytest

from core.evaluators import EVALUATOR_REGISTRY
from core.evaluators.builtin import BUILTIN_EVALUATOR_FACTORIES
from core.evaluators.ifeval_check import IfevalCheckEvaluator
from core import nltk_data


def _verifiers_available():
    for mod in ("nltk", "langdetect", "emoji", "syllapy", "immutabledict"):
        if importlib.util.find_spec(mod) is None:
            return f"extra 'ifeval' not installed ({mod})"
    import nltk

    dirs = nltk_data.search_dirs(extra=nltk.data.path)
    absent = nltk_data.missing(dirs)
    if absent:
        return f"nltk data missing {absent}; set NLTK_DATA or run `eva data fetch`"
    return None


_SKIP = _verifiers_available()
needs_verifiers = pytest.mark.skipif(_SKIP is not None, reason=_SKIP or "")


def case(ids, kwargs=None, prompt="p"):
    meta = {"instruction_id_list": ids}
    if kwargs is not None:
        meta["kwargs"] = kwargs
    return {"id": "c", "input": prompt, "metadata": meta}


def run(resp, ids, kwargs=None, **cfg):
    return IfevalCheckEvaluator(**cfg).run_case(resp, case(ids, kwargs))


def test_registered_everywhere():
    assert EVALUATOR_REGISTRY["ifeval_check"] is IfevalCheckEvaluator
    assert isinstance(BUILTIN_EVALUATOR_FACTORIES["ifeval_check"]({}, None), IfevalCheckEvaluator)


def test_not_applicable_without_instruction_ids():
    assert IfevalCheckEvaluator().run_case("x", {"metadata": {}}) is None
    assert IfevalCheckEvaluator().run_case("x", {}) is None


def test_bad_pass_on_rejected():
    with pytest.raises(ValueError):
        IfevalCheckEvaluator(pass_on="medium")


def test_missing_extra_names_install_command(monkeypatch):
    import core.evaluators.ifeval_check as mod

    monkeypatch.setattr(mod, "_registry", None)
    monkeypatch.setitem(sys.modules, "langdetect", None)  # import -> ImportError
    s = run("hello", ["detectable_format:json_format"], [{}])
    assert s.value == 0.0
    assert 'pip install "hop-top-eva[ifeval]"' in s.reason


def test_missing_nltk_data_names_fetch_command(monkeypatch, tmp_path):
    pytest.importorskip("nltk")
    pytest.importorskip("langdetect")
    pytest.importorskip("emoji")
    pytest.importorskip("syllapy")
    pytest.importorskip("immutabledict")
    import core.evaluators.ifeval_check as mod
    import nltk

    monkeypatch.setattr(mod, "_registry", None)
    monkeypatch.setattr(nltk.data, "path", [])
    monkeypatch.setenv("NLTK_DATA", str(tmp_path / "empty"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    s = run("hello", ["detectable_format:json_format"], [{}])
    assert s.value == 0.0
    assert "eva data fetch" in s.reason and "punkt_tab" in s.reason


def test_malformed_metadata_is_error():
    s = IfevalCheckEvaluator().run_case("x", {"metadata": {"instruction_id_list": "a"}})
    assert s.value == 0.0 and s.reason.startswith("error:")
    s = run("x", ["a", "b"], [{}])
    assert s.value == 0.0 and "kwargs" in s.reason


@needs_verifiers
def test_unknown_instruction_id_is_error_not_pass():
    s = run("anything", ["no_such:instruction"], [{}])
    assert s.value == 0.0
    assert "unknown instruction id" in s.reason and "no_such:instruction" in s.reason
    assert s.metadata.get("error")


@needs_verifiers
def test_unknown_id_alongside_valid_ids_still_error():
    s = run('{"a": 1}', ["detectable_format:json_format", "bogus:id"], [{}, {}])
    assert s.value == 0.0 and "bogus:id" in s.reason


@needs_verifiers
def test_word_count():
    ids = ["length_constraints:number_words"]
    kw = [{"relation": "at least", "num_words": 5}]
    assert run("one two three four five six", ids, kw).value == 1.0
    s = run("one two", ids, kw)
    assert s.value == 0.0 and "length_constraints:number_words" in s.reason


@needs_verifiers
def test_keyword_inclusion_and_exclusion():
    inc = ["keywords:existence"]
    assert run("The alpha wolf.", inc, [{"keywords": ["alpha"]}]).value == 1.0
    assert run("The beta wolf.", inc, [{"keywords": ["alpha"]}]).value == 0.0
    exc = ["keywords:forbidden_words"]
    assert run("A nice day.", exc, [{"forbidden_words": ["bad"]}]).value == 1.0
    assert run("A bad day.", exc, [{"forbidden_words": ["bad"]}]).value == 0.0


@needs_verifiers
def test_json_format():
    ids = ["detectable_format:json_format"]
    assert run('```json\n{"a": 1}\n```', ids, [{}]).value == 1.0
    assert run("not json at all", ids, [{}]).value == 0.0


@needs_verifiers
def test_paragraph_count():
    ids = ["length_constraints:number_paragraphs"]
    kw = [{"num_paragraphs": 3}]
    assert run("one\n***\ntwo\n***\nthree", ids, kw).value == 1.0
    assert run("one\n***\ntwo", ids, kw).value == 0.0


@needs_verifiers
def test_language():
    ids = ["language:response_language"]
    fr = "Bonjour à tous, nous espérons que vous allez bien aujourd'hui et que le soleil brille."
    assert run(fr, ids, [{"language": "fr"}]).value == 1.0
    assert run("Hello everyone, we hope you are doing well today and that the sun is shining.",
               ids, [{"language": "fr"}]).value == 0.0


@needs_verifiers
def test_ifbench_out_of_distribution_constraints():
    assert run("I have 3 apples, 5 pears and 12 plums.", ["count:numbers"], [{"N": 3}]).value == 1.0
    assert run("I have 3 apples and 5 pears.", ["count:numbers"], [{"N": 3}]).value == 0.0
    assert run("nowhitespacehere", ["format:no_whitespace"], [{}]).value == 1.0
    assert run("has whitespace", ["format:no_whitespace"], [{}]).value == 0.0


@needs_verifiers
def test_null_kwargs_are_dropped_like_ifbench_data():
    # IFBench rows carry every kwarg key, null where unused.
    s = run("a b c 1 2 3", ["count:numbers"], [{"N": 3, "min_words": None, "language": None}])
    assert s.value == 1.0


@needs_verifiers
def test_prompt_level_all_instructions_must_pass():
    ids = ["detectable_format:json_format", "keywords:existence"]
    kw = [{}, {"keywords": ["alpha"]}]
    assert run('```json\n{"x": "alpha"}\n```', ids, kw).value == 1.0
    s = run('```json\n{"x": "beta"}\n```', ids, kw)
    assert s.value == 0.0
    assert "detectable_format:json_format strict=pass" in s.reason
    assert "keywords:existence strict=fail" in s.reason


@needs_verifiers
def test_strict_and_loose_differ_and_pass_on_selects():
    # The intro line holds an extra number: strict counts 4, loose drops the line.
    ids, kw = ["count:numbers"], [{"N": 3}]
    resp = "Here are 4 numbers:\n1 2 3"
    strict = run(resp, ids, kw)
    loose = run(resp, ids, kw, pass_on="loose")
    assert strict.metadata["strict"] is False and strict.metadata["loose"] is True
    assert strict.value == 0.0
    assert loose.value == 1.0
    assert "strict fail" in strict.reason and "loose pass" in strict.reason


@needs_verifiers
def test_empty_reply_fails():
    s = run("   ", ["format:no_whitespace"], [{}])
    assert s.value == 0.0 and s.metadata["loose"] is False


@needs_verifiers
def test_reasoning_block_is_not_graded():
    s = run("<think>one two three four five six seven</think>short", ["length_constraints:number_words"],
            [{"relation": "at least", "num_words": 5}])
    assert s.value == 0.0


@needs_verifiers
def test_prompt_arg_comes_from_case_input():
    ids = ["combination:repeat_prompt"]
    kw = [{"prompt_to_repeat": "Write a poem"}]
    ok = IfevalCheckEvaluator().run_case("Write a poem\nRoses are red.", case(ids, kw, prompt="Write a poem"))
    assert ok.value == 1.0


@needs_verifiers
def test_evaluation_never_downloads_or_opens_sockets(monkeypatch):
    import socket

    import nltk
    import core.evaluators.ifeval_check as mod

    def boom(*a, **k):
        raise AssertionError("network/download attempted during evaluation")

    monkeypatch.setattr(nltk, "download", boom)
    monkeypatch.setattr(socket.socket, "connect", boom)
    monkeypatch.setattr(mod, "_registry", None)
    s = run("One sentence. Two sentences.", ["length_constraints:number_sentences"],
            [{"relation": "at least", "num_sentences": 2}])
    assert s.value == 1.0
