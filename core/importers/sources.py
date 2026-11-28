# core/importers/sources.py
"""Public benchmark sets as eva cases.

Every source is a deterministic stream of cases. ``Ctx.order`` fixes the
visiting order of the upstream rows from the seed and the row index alone,
never from how many cases are wanted, so taking the first N of a stream
always extends the first M < N. Row -> case functions are pure; the
streams do the fetching. Ids come from the upstream row identity.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from core.importers.fetch import Fetcher, RowTruncated

CATEGORY = "category"
FINAL = "End your reply with a line of the form `Final answer: {form}`."
CODE_REPLY = (
    "Reply with a single ```python code block containing the full implementation "
    "and nothing else after it. No tests, no prints."
)
# EvalPlus harnesses import numpy for float comparison only; eva's code_tests
# environment has none, so a small stand-in keeps the cases self-contained.
NP_SHIM = '''class np:
    class ndarray: pass
    float64 = float32 = float
    @staticmethod
    def allclose(a, b, rtol=1e-07, atol=0):
        if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
            return len(a) == len(b) and all(np.allclose(x, y, rtol, atol) for x, y in zip(a, b))
        try:
            return abs(a - b) <= atol + rtol * abs(b)
        except TypeError:
            return a == b
'''
SUMMEDITS_MAX_DOC = 12000
HUMANEVAL_MAX_TEST = 60000
MBPP_MAX_TEST = 30000
ZEBRA_MAX_GRID = 5


@dataclass
class Ctx:
    fx: Fetcher
    seed: str
    today: str
    rev: str = ""           # upstream revision, filled in by the runner
    verify: Callable[[str, dict], bool] | None = None

    def order(self, total: int, key: str) -> list[int]:
        """Row indices in a seeded order that depends on nothing but the key."""
        tag = f"{key}:{self.seed}"
        return sorted(range(total), key=lambda i: hashlib.sha256(f"{tag}:{i}".encode()).digest())


@dataclass(frozen=True)
class Source:
    name: str
    upstream: str                 # dataset id / repo
    kind: str                     # hf | git
    category: str
    evaluator: str
    stream: Callable[[Ctx], Iterator[dict]] | None
    licence: str | None           # what cases are stamped with; None = refuse
    card_licence: str | None = None   # Hub card tag to re-check at import time
    refusal: str = ""


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")


def round_robin(streams: list[Iterator[dict]]) -> Iterator[dict]:
    live = list(streams)
    while live:
        for it in list(live):
            try:
                yield next(it)
            except StopIteration:
                live.remove(it)


def meta(ctx: Ctx, source: Source, ref: str, **extra) -> dict:
    return {
        "category": source.category,
        "source": f"{source.upstream}:{ref}@{ctx.rev[:12]}",
        "licence": source.licence,
        "added": ctx.today,
        "origin": "import",
        **extra,
    }


def _rows(ctx: Ctx, dataset: str, config: str, split: str, key: str) -> Iterator[tuple[int, dict]]:
    total = ctx.fx.total(dataset, config, split)
    for idx in ctx.order(total, key):
        try:
            yield idx, ctx.fx.row(dataset, config, split, idx)
        except RowTruncated:
            continue


# ---- BABILong: long context ---------------------------------------------------------------

def babilong_case(ctx: Ctx, source: Source, row: dict, config: str, split: str, idx: int) -> dict:
    return {
        "id": f"babilong-{config}-{split}-{idx:03d}",
        "input": (f"{row['input']}\n\nQuestion: {row['question'].strip()}\n"
                  "Answer from the facts stated in the text above, with a single word. "
                  + FINAL.format(form="<word>")),
        "expected_output": row["target"].strip(),
        "metadata": meta(ctx, source, f"{config}/{split}#{idx}", context=config, task=split),
    }


def babilong_stream(ctx: Ctx) -> Iterator[dict]:
    src = SOURCES["babilong"]
    cells = [(c, f"qa{q}") for c in ("8k", "16k") for q in range(1, 6)]

    def cell(config: str, split: str) -> Iterator[dict]:
        for idx, row in _rows(ctx, src.upstream, config, split, f"babilong:{config}:{split}"):
            yield babilong_case(ctx, src, row, config, split, idx)

    return round_robin([cell(c, s) for c, s in cells])


# ---- MMLU-Pro: reasoning ------------------------------------------------------------------

def mmlupro_case(ctx: Ctx, source: Source, row: dict) -> dict:
    letters = "ABCDEFGHIJ"
    opts = "\n".join(f"{letters[i]}. {o}" for i, o in enumerate(row["options"]))
    qid = row["question_id"]
    return {
        "id": f"mmlupro-{qid}",
        "input": f"{row['question'].strip()}\n\n{opts}\n\n" + FINAL.format(form="<letter>"),
        "expected_output": row["answer"],
        "metadata": meta(ctx, source, f"test#{qid}", subject=row["category"]),
    }


def mmlupro_stream(ctx: Ctx) -> Iterator[dict]:
    src = SOURCES["mmlupro"]
    for _, row in _rows(ctx, src.upstream, "default", "test", "mmlupro"):
        yield mmlupro_case(ctx, src, row)


# ---- SummEdits: summarising ---------------------------------------------------------------

def summedits_case(ctx: Ctx, source: Source, row: dict) -> dict:
    return {
        "id": f"summedits-{slug(row['id'])}",
        "input": ("Decide whether the summary is factually consistent with the document: every "
                  "statement in the summary must be supported by the document.\n\n"
                  f"Document:\n{row['doc'].strip()}\n\nSummary:\n{row['summary'].strip()}\n\n"
                  + FINAL.format(form="consistent` or `Final answer: inconsistent")),
        "expected_output": "consistent" if row["label"] == 1 else "inconsistent",
        "metadata": meta(ctx, source, f"train#{row['id']}", domain=row["domain"]),
    }


def summedits_stream(ctx: Ctx) -> Iterator[dict]:
    """Consistent and inconsistent alternate; documents of at most 12,000 characters."""
    src = SOURCES["summedits"]
    scan = _rows(ctx, src.upstream, "default", "train", "summedits")
    bufs: dict[int, list[dict]] = {1: [], 0: []}
    want = 1
    done = False
    while True:
        while not bufs[want] and not done:
            nxt = next(scan, None)
            if nxt is None:
                done = True
                break
            row = nxt[1]
            if len(row["doc"]) <= SUMMEDITS_MAX_DOC and row["label"] in bufs:
                bufs[row["label"]].append(summedits_case(ctx, src, row))
        if bufs[want]:
            yield bufs[want].pop(0)
        elif bufs[1 - want]:
            yield bufs[1 - want].pop(0)
        else:
            return
        want = 1 - want


# ---- coding: EvalPlus ---------------------------------------------------------------------

def shim_numpy(test: str) -> str:
    return test.replace("import numpy as np\n", NP_SHIM, 1)


def humaneval_case(ctx: Ctx, source: Source, row: dict) -> tuple[dict, str]:
    """(case, the dataset's own reference solution)."""
    num = int(row["task_id"].split("/")[-1])
    case = {
        "id": f"humanevalplus-{num:03d}",
        "input": (f"Complete this Python function.\n\n```python\n{row['prompt'].rstrip()}\n```\n\n"
                  "Reply with a single ```python code block containing the full function, with "
                  "its signature, imports and any helpers, and nothing else after it. "
                  "No tests, no prints."),
        "tests": shim_numpy(row["test"]).strip() + f"\n\ncheck({row['entry_point']})\n",
        "metadata": meta(ctx, source, f"test#{row['task_id']}"),
    }
    return case, row["prompt"] + row["canonical_solution"]


def mbpp_name(row: dict) -> str | None:
    names = re.findall(r"^def (\w+)\(", row["code"], re.M)
    first = row["test_list"][0] if row["test_list"] else ""
    for nm in names:
        if re.search(rf"\b{re.escape(nm)}\(", first):
            return nm
    return names[-1] if names else None


def mbpp_case(ctx: Ctx, source: Source, row: dict) -> tuple[dict | None, str]:
    """(case, reference solution); case is None when the function name is not found."""
    name = mbpp_name(row)
    if not name or not row["test_list"]:
        return None, ""
    case = {
        "id": f"mbppplus-{int(row['task_id']):04d}",
        "input": (f"{row['prompt'].strip()}\n\nThe function must be named `{name}` and pass "
                  f"this check:\n{row['test_list'][0]}\n\n{CODE_REPLY}"),
        "tests": "\n".join(row.get("test_imports") or []) + "\n"
                 + shim_numpy(row["test"]).strip() + "\n",
        "metadata": meta(ctx, source, f"test#{row['task_id']}"),
    }
    return case, row["code"]


def _coding(ctx: Ctx, name: str, to_case, max_test: int) -> Iterator[dict]:
    src = SOURCES[name]
    for _, row in _rows(ctx, src.upstream, "default", "test", name):
        if len(row["test"]) > max_test:
            continue
        case, ref = to_case(ctx, src, row)
        # Admit a case only when the dataset's own solution passes the tests
        # exactly as the code_tests evaluator will run them.
        if case and ctx.verify and ctx.verify(ref, case):
            yield case


def humanevalplus_stream(ctx: Ctx) -> Iterator[dict]:
    return _coding(ctx, "humanevalplus", humaneval_case, HUMANEVAL_MAX_TEST)


def mbppplus_stream(ctx: Ctx) -> Iterator[dict]:
    return _coding(ctx, "mbppplus", mbpp_case, MBPP_MAX_TEST)


# ---- Natural Plan: executive assistant ----------------------------------------------------

_SLOT = re.compile(r"(\w+day),\s*(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})")


def naturalplan_case(ctx: Ctx, source: Source, key: str, row: dict) -> dict | None:
    m = _SLOT.search(row["golden_plan"])
    if not m:
        return None
    return {
        "id": f"naturalplan-{slug(key)}",
        "input": (f"{row['prompt_0shot'].strip()}\n\nEnd your reply with a line of exactly this "
                  "form, 24-hour times: `Final answer: <Day>, <HH:MM> - <HH:MM>`."),
        "expected_output": f"{m.group(1)}, {m.group(2)} - {m.group(3)}",
        "metadata": meta(ctx, source, f"calendar_scheduling#{key}",
                         people=row.get("num_people"), days=row.get("num_days")),
    }


def naturalplan_stream(ctx: Ctx) -> Iterator[dict]:
    """Calendar scheduling, spread evenly over the number of attendees."""
    src = SOURCES["naturalplan"]
    data = ctx.fx.raw_json(src.upstream, ctx.rev, "data/calendar_scheduling.json")
    groups: dict[str, list[str]] = {}
    for k in sorted(data):
        groups.setdefault(str(data[k].get("num_people")), []).append(k)

    def one(g: str) -> Iterator[dict]:
        ks = sorted(groups[g], key=lambda k: hashlib.sha256(
            f"naturalplan:{g}:{ctx.seed}:{k}".encode()).digest())
        for k in ks:
            c = naturalplan_case(ctx, src, k, data[k])
            if c:
                yield c

    return round_robin([one(g) for g in sorted(groups)])


SOURCES: dict[str, Source] = {s.name: s for s in [
    Source("babilong", "RMT-team/babilong", "hf", "long-context", "final_answer",
           babilong_stream, "Apache-2.0; BSD (bAbI)"),
    Source("mmlupro", "TIGER-Lab/MMLU-Pro", "hf", "reasoning", "final_answer",
           mmlupro_stream, "MIT", card_licence="mit"),
    Source("summedits", "Salesforce/summedits", "hf", "summarizing", "final_answer",
           summedits_stream, "CC-BY-4.0", card_licence="cc-by-4.0"),
    Source("humanevalplus", "evalplus/humanevalplus", "hf", "coding", "code_tests",
           humanevalplus_stream, "Apache-2.0", card_licence="apache-2.0"),
    Source("mbppplus", "evalplus/mbppplus", "hf", "coding", "code_tests",
           mbppplus_stream, "Apache-2.0", card_licence="apache-2.0"),
    Source("naturalplan", "google-deepmind/natural-plan", "git", "executive-assistant",
           "final_answer", naturalplan_stream, "CC-BY-4.0"),
    Source("zebralogic", "WildEval/ZebraLogic", "hf", "reasoning", "final_answer", None, None,
           refusal="its dataset card states no licence; import it only after a licence "
                   "is confirmed upstream"),
]}
