"""Dataset importers: row -> case mapping, ids, provenance, seeded sampling
that only appends, dry-run, re-import and network failure. No network: the
fetcher is replaced by recorded rows (tests/fixtures/importers)."""
import copy
import itertools
import json
import urllib.error
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from cli.dataset_cmd import dataset_app
from core import importers
from core.append_only import check
from core.dataset import case_hash
from core.importers import ImportRefused, import_source, reference_passes
from core.importers import sources as S
from core.importers.fetch import Fetcher, FetchError

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "importers"
TODAY = "2026-11-27"
REV = "a" * 40
NAMES = ["babilong", "mmlupro", "summedits", "humanevalplus", "mbppplus", "naturalplan"]
CARD = {"mmlupro": "mit", "summedits": "cc-by-4.0", "humanevalplus": "apache-2.0",
        "mbppplus": "apache-2.0"}


class FakeFetcher:
    """Serves the recorded rows of one source; position in the list is the row index."""

    def __init__(self, name, card=None):
        self.data = json.loads((FIX / f"{name}.json").read_text())
        self.card = CARD.get(name) if card is None else card
        self.calls = 0

    def total(self, dataset, config, split):
        return len(self.data.get(f"{config}/{split}", []))

    def row(self, dataset, config, split, idx):
        self.calls += 1
        return copy.deepcopy(self.data[f"{config}/{split}"][idx])

    def hub_card(self, dataset):
        return REV, self.card

    def git_head(self, repo):
        return REV

    def raw_json(self, repo, rev, path):
        assert rev == REV
        return copy.deepcopy(self.data)


def make_dataset(tmp_path, append_only=True):
    d = tmp_path / "pool"
    d.mkdir()
    (d / "dataset.yaml").write_text(yaml.safe_dump(
        {"name": "pool", "target": "http://127.0.0.1:9/chat", "append_only": append_only}))
    return d


def snapshot(d):
    return {p.name: p.read_bytes() for p in sorted(d.iterdir())}


def run(name, d, n, seed="0", **kw):
    kw.setdefault("fx", FakeFetcher(name))
    return import_source(name, d, n, seed, TODAY, **kw)


def stream(name, seed="0", fx=None):
    ctx = S.Ctx(fx=fx or FakeFetcher(name), seed=seed, today=TODAY, rev=REV,
                verify=lambda ref, case: True)
    return S.SOURCES[name].stream(ctx)


def lines(d, name):
    return (d / f"{name}.jsonl").read_text().splitlines()


# ---- row -> case mapping ----------------------------------------------------------------

def ctx_for(name):
    fx = FakeFetcher(name)
    return fx, S.Ctx(fx=fx, seed="0", today=TODAY, rev=REV), S.SOURCES[name]


def test_babilong_mapping():
    fx, ctx, src = ctx_for("babilong")
    row = fx.row("", "8k", "qa1", 1)
    c = S.babilong_case(ctx, src, row, "8k", "qa1", 1)
    assert c["id"] == "babilong-8k-qa1-001"
    assert c["expected_output"] == row["target"].strip()
    assert c["input"].startswith(row["input"])
    assert f"Question: {row['question'].strip()}" in c["input"]
    assert c["input"].rstrip().endswith("`Final answer: <word>`.")
    assert c["metadata"]["category"] == "long-context"
    assert (c["metadata"]["context"], c["metadata"]["task"]) == ("8k", "qa1")
    assert c["metadata"]["source"] == f"RMT-team/babilong:8k/qa1#1@{REV[:12]}"


def test_mmlupro_mapping():
    fx, ctx, src = ctx_for("mmlupro")
    row = fx.row("", "default", "test", 0)
    c = S.mmlupro_case(ctx, src, row)
    assert c["id"] == f"mmlupro-{row['question_id']}"
    assert c["expected_output"] == row["answer"] and row["answer"] in "ABCDEFGHIJ"
    for i, o in enumerate(row["options"]):
        assert f"{'ABCDEFGHIJ'[i]}. {o}" in c["input"]
    assert c["metadata"]["subject"] == row["category"]
    assert c["metadata"]["category"] == "reasoning"


def test_summedits_mapping_labels():
    fx, ctx, src = ctx_for("summedits")
    rows = fx.data["default/train"]
    pos = next(r for r in rows if r["label"] == 1)
    neg = next(r for r in rows if r["label"] == 0)
    cp, cn = S.summedits_case(ctx, src, pos), S.summedits_case(ctx, src, neg)
    assert cp["expected_output"] == "consistent" and cn["expected_output"] == "inconsistent"
    assert cp["id"] == "summedits-" + S.slug(pos["id"])
    assert cp["metadata"]["category"] == "summarizing"
    assert "Final answer: consistent` or `Final answer: inconsistent" in cp["input"]


def test_humaneval_mapping_and_reference():
    fx, ctx, src = ctx_for("humanevalplus")
    row = fx.data["default/test"][0]
    case, ref = S.humaneval_case(ctx, src, row)
    n = int(row["task_id"].split("/")[-1])
    assert case["id"] == f"humanevalplus-{n:03d}"
    assert case["tests"].rstrip().endswith(f"check({row['entry_point']})")
    assert "import numpy" not in case["tests"]
    assert ref == row["prompt"] + row["canonical_solution"]
    assert case["metadata"]["category"] == "coding"
    assert reference_passes(ref, case)
    assert not reference_passes("def broken(:\n", case)


def test_mbpp_mapping_and_reference():
    fx, ctx, src = ctx_for("mbppplus")
    for row in fx.data["default/test"]:
        case, ref = S.mbpp_case(ctx, src, row)
        assert case["id"] == f"mbppplus-{int(row['task_id']):04d}"
        assert f"`{S.mbpp_name(row)}`" in case["input"]
        assert row["test_list"][0] in case["input"]
        assert "import numpy" not in case["tests"]
        assert reference_passes(ref, case), row["task_id"]


def test_naturalplan_mapping():
    fx, ctx, src = ctx_for("naturalplan")
    key = sorted(fx.data)[0]
    c = S.naturalplan_case(ctx, src, key, fx.data[key])
    assert c["id"] == "naturalplan-" + S.slug(key)
    assert S._SLOT.fullmatch(c["expected_output"])
    assert c["expected_output"] in fx.data[key]["golden_plan"].replace("Here is the proposed time: ", "")
    assert c["metadata"]["people"] == fx.data[key]["num_people"]
    assert S.naturalplan_case(ctx, src, "k", {**fx.data[key], "golden_plan": "none"}) is None


# ---- provenance ----------------------------------------------------------------------------

@pytest.mark.parametrize("name", NAMES)
def test_every_case_carries_provenance(name):
    src = S.SOURCES[name]
    cases = list(itertools.islice(stream(name), 4))
    assert cases
    for c in cases:
        m = c["metadata"]
        assert m["licence"] == src.licence and m["licence"]
        assert m["origin"] == "import" and m["added"] == TODAY
        assert m["category"] == src.category
        assert m["source"].startswith(src.upstream + ":") and m["source"].count("@") == 1
        assert f"@{REV[:12]}" in m["source"]


@pytest.mark.parametrize("name", NAMES)
def test_import_passes_dataset_check(tmp_path, name):
    d = make_dataset(tmp_path)
    run(name, d, 3)
    res = check(d)
    assert res.ok, [p.message for p in res.problems]
    assert res.cases == 3


# ---- ids and sampling -----------------------------------------------------------------------

@pytest.mark.parametrize("name", NAMES)
def test_larger_sample_only_appends(tmp_path, name):
    d = make_dataset(tmp_path)
    first = run(name, d, 1)
    before = lines(d, name)
    lock_before = json.loads((d / "dataset.lock.json").read_text())["cases"]
    second = run(name, d, 3)
    after = lines(d, name)
    assert len(first.added) == 1 and len(second.added) == 2 and len(second.skipped) == 1
    assert after[:1] == before            # byte-identical prefix
    assert second.added == [json.loads(x)["id"] for x in after[1:]]
    lock_after = json.loads((d / "dataset.lock.json").read_text())["cases"]
    assert {k: lock_after[k] for k in lock_before} == lock_before
    assert check(d).ok


@pytest.mark.parametrize("name", NAMES)
def test_order_is_independent_of_n_and_repeatable(name):
    full = [c["id"] for c in stream(name)]
    assert [c["id"] for c in itertools.islice(stream(name), 3)] == full[:3]
    assert [c["id"] for c in stream(name)] == full


def test_seed_changes_order_not_identity():
    a = {c["id"]: case_hash(c) for c in stream("mmlupro", "1")}
    b = {c["id"]: case_hash(c) for c in stream("mmlupro", "2")}
    assert [c["id"] for c in stream("mmlupro", "1")] != [c["id"] for c in stream("mmlupro", "2")]
    assert a == b  # a row keeps its id and hash whatever its position in the sample


def test_ids_come_from_upstream_row_not_position():
    fx = FakeFetcher("mmlupro")
    qids = {r["question_id"] for r in fx.data["default/test"]}
    ids = {c["id"] for c in stream("mmlupro", "9", fx)}
    assert ids == {f"mmlupro-{q}" for q in qids}
    hs = [c["id"] for c in stream("humanevalplus", "3")]
    nums = {int(r["task_id"].split("/")[-1]) for r in FakeFetcher("humanevalplus").data["default/test"]}
    assert {int(i.split("-")[-1]) for i in hs} == nums


def test_babilong_round_robin_over_cells():
    ids = [c["id"] for c in itertools.islice(stream("babilong"), 2)]
    assert {i.rsplit("-", 1)[0] for i in ids} == {"babilong-8k-qa1", "babilong-8k-qa2"}


def test_naturalplan_spread_over_attendees():
    people = [c["metadata"]["people"] for c in itertools.islice(stream("naturalplan"), 3)]
    assert sorted(people) == ["2", "3", "4"]


def test_summedits_balanced_and_length_capped():
    fx = FakeFetcher("summedits")
    long = copy.deepcopy(fx.data["default/train"][0])
    long.update(id="long-one", label=1, doc="x" * (S.SUMMEDITS_MAX_DOC + 1))
    fx.data["default/train"].append(long)
    out = list(stream("summedits", fx=fx))
    assert "summedits-long-one" not in {c["id"] for c in out}
    first6 = [c["expected_output"] for c in out[:6]]
    assert first6 == ["consistent", "inconsistent"] * 3


def test_coding_admits_only_verified_references():
    fx = FakeFetcher("humanevalplus")
    seen = []

    def verify(ref, case):
        seen.append(case["id"])
        return len(seen) != 1   # reject the first candidate

    ctx = S.Ctx(fx=fx, seed="0", today=TODAY, rev=REV, verify=verify)
    out = list(S.SOURCES["humanevalplus"].stream(ctx))
    assert len(out) == len(seen) - 1 and seen[0] not in {c["id"] for c in out}


def test_coding_skips_oversized_tests():
    fx = FakeFetcher("mbppplus")
    fx.data["default/test"] = [dict(r, test=r["test"] + "#" * S.MBPP_MAX_TEST)
                               for r in fx.data["default/test"]]
    assert list(stream("mbppplus", fx=fx)) == []


# ---- re-import, dry-run ---------------------------------------------------------------------

@pytest.mark.parametrize("name", ["mmlupro", "naturalplan"])
def test_reimport_is_noop(tmp_path, name):
    d = make_dataset(tmp_path)
    run(name, d, 3)
    snap = snapshot(d)
    again = import_source(name, d, 3, "0", "2027-01-01", fx=FakeFetcher(name))
    assert again.added == [] and len(again.skipped) == 3 and not again.problems
    assert snapshot(d) == snap


def test_dry_run_writes_nothing(tmp_path):
    d = make_dataset(tmp_path)
    snap = snapshot(d)
    res = run("mmlupro", d, 3, dry_run=True)
    assert len(res.added) == 3
    assert snapshot(d) == snap


# ---- refusal and failure --------------------------------------------------------------------

def test_source_without_verified_licence_is_refused(tmp_path):
    d = make_dataset(tmp_path)
    fx = FakeFetcher("mmlupro")
    with pytest.raises(ImportRefused, match="licence"):
        import_source("zebralogic", d, 3, "0", TODAY, fx=fx)
    assert fx.calls == 0 and snapshot(d) == {"dataset.yaml": (d / "dataset.yaml").read_bytes()}


def test_card_licence_change_is_refused(tmp_path):
    d = make_dataset(tmp_path)
    with pytest.raises(ImportRefused, match="CC-BY-NC|cc-by-nc"):
        run("mmlupro", d, 3, fx=FakeFetcher("mmlupro", card="cc-by-nc-4.0"))
    with pytest.raises(ImportRefused):
        run("mmlupro", d, 3, fx=FakeFetcher("mmlupro", card=""))
    assert not (d / "mmlupro.jsonl").exists()


def test_unknown_source_and_plain_dataset(tmp_path):
    d = make_dataset(tmp_path)
    with pytest.raises(ImportRefused, match="unknown source"):
        import_source("nope", d, 3, "0", TODAY)
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "dataset.yaml").write_text(yaml.safe_dump({"name": "p", "target": "http://x/chat"}))
    fx = FakeFetcher("mmlupro")
    with pytest.raises(ValueError, match="append-only"):
        import_source("mmlupro", plain, 3, "0", TODAY, fx=fx)
    assert fx.calls == 0


class FailingAfter(FakeFetcher):
    def row(self, *a):
        if self.calls >= 2:
            raise FetchError("boom")
        return super().row(*a)


def test_fetch_failure_writes_nothing(tmp_path):
    d = make_dataset(tmp_path)
    snap = snapshot(d)
    with pytest.raises(FetchError):
        run("mmlupro", d, 5, fx=FailingAfter("mmlupro", card="mit"))
    assert snapshot(d) == snap


def test_fetcher_retries_then_fails(monkeypatch):
    calls, naps = [], []

    def boom(req, timeout=0):
        calls.append(req.full_url)
        raise urllib.error.URLError("down")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    fx = Fetcher(delay=0, tries=3, sleep=naps.append)
    with pytest.raises(FetchError, match="down"):
        fx.row("a/b", "default", "test", 0)
    assert len(calls) == 3
    assert "datasets-server.huggingface.co" in calls[0]


def test_fetcher_user_agent_names_no_person(monkeypatch):
    seen = {}

    class R:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps({"num_rows_total": 1, "rows": [{"row": {"x": 1}}]}).encode()

    def ok(req, timeout=0):
        seen["ua"] = req.get_header("User-agent")
        return R()

    monkeypatch.setattr("urllib.request.urlopen", ok)
    assert Fetcher(delay=0, sleep=lambda s: None).row("a/b", "default", "test", 0) == {"x": 1}
    assert seen["ua"].startswith("eva-dataset-importer")


def test_fetcher_rate_limit_honours_retry_after(monkeypatch):
    naps, n = [], []

    class R:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps({"num_rows_total": 1, "rows": [{"row": {"x": 1}}]}).encode()

    def flaky(req, timeout=0):
        n.append(1)
        if len(n) == 1:
            raise urllib.error.HTTPError(req.full_url, 429, "slow", {"Retry-After": "7"}, None)
        return R()

    monkeypatch.setattr("urllib.request.urlopen", flaky)
    assert Fetcher(delay=0, sleep=naps.append).row("a/b", "default", "test", 0) == {"x": 1}
    assert 7.0 in naps


def test_fetcher_viewer_truncated_cell_is_reported(monkeypatch):
    class R:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self):
            return json.dumps({"num_rows_total": 1,
                               "rows": [{"row": {"x": 1}, "truncated_cells": ["x"]}]}).encode()

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=0: R())
    with pytest.raises(FetchError, match="truncated"):
        Fetcher(delay=0, sleep=lambda s: None).row("a/b", "default", "test", 0)


# ---- CLI --------------------------------------------------------------------------------------

def cli(*args):
    return CliRunner().invoke(dataset_app, ["import", *args])


@pytest.fixture
def fake_net(monkeypatch):
    monkeypatch.setattr(importers, "Fetcher", lambda: FakeFetcher("mmlupro"))


def test_cli_import_json_and_exit_codes(tmp_path, fake_net):
    d = make_dataset(tmp_path)
    r = cli("mmlupro", "--into", str(d), "--n", "3", "--format", "json")
    assert r.exit_code == 0, r.output
    out = json.loads(r.stdout)
    assert out["ok"] and len(out["added"]) == 3 and out["sampled"] == 3 and out["revision"] == REV
    r2 = cli("mmlupro", "--into", str(d), "--n", "3", "--format", "json")
    assert r2.exit_code == 0 and json.loads(r2.stdout)["added"] == []
    assert cli("mmlupro", "--into", str(d), "--format", "xml").exit_code == 2
    assert cli("zebralogic", "--into", str(d)).exit_code == 2
    assert cli("nope", "--into", str(d)).exit_code == 2
    assert cli("mmlupro", "--into", str(tmp_path / "missing")).exit_code == 2


def test_cli_dry_run_writes_nothing(tmp_path, fake_net):
    d = make_dataset(tmp_path)
    snap = snapshot(d)
    r = cli("mmlupro", "--into", str(d), "--n", "2", "--dry-run", "--format", "json")
    assert r.exit_code == 0 and json.loads(r.stdout)["dry_run"] is True
    assert len(json.loads(r.stdout)["added"]) == 2
    assert snapshot(d) == snap


def test_cli_conflicting_case_exits_3(tmp_path, fake_net):
    d = make_dataset(tmp_path)
    assert cli("mmlupro", "--into", str(d), "--n", "1").exit_code == 0
    p = d / "mmlupro.jsonl"
    rec = json.loads(p.read_text())
    p.write_text("")  # remove, then add a different case under the same id
    other = dict(rec, input="edited")
    p.write_text(json.dumps(other) + "\n")
    (d / "dataset.lock.json").write_text(json.dumps(
        {"version": 1, "algorithm": "sha256", "cases": {rec["id"]: case_hash(rec)}}))
    r = cli("mmlupro", "--into", str(d), "--n", "1")
    assert r.exit_code == 3


def test_cli_network_failure_exits_1_and_writes_nothing(tmp_path, monkeypatch):
    def down(req, timeout=0):
        raise urllib.error.URLError("no route")

    monkeypatch.setattr("urllib.request.urlopen", down)
    monkeypatch.setattr(importers, "Fetcher", lambda: Fetcher(delay=0, tries=2, sleep=lambda s: None))
    d = make_dataset(tmp_path)
    snap = snapshot(d)
    r = cli("mmlupro", "--into", str(d), "--n", "3")
    assert r.exit_code == 1
    assert "nothing written" in r.output
    assert snapshot(d) == snap
