# core/importers/__init__.py
"""Import public benchmark sets into an append-only directory dataset.

``import_source`` fetches, maps and samples first, then appends through
``core.append_only.add``: nothing is written when any fetch fails, and
re-importing is a no-op because ``add`` skips cases whose id and content
hash are already present.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from pathlib import Path

from core.append_only import Problem, add, check
from core.importers.fetch import Fetcher, FetchError
from core.importers.sources import SOURCES, Ctx, Source

__all__ = ["SOURCES", "FetchError", "ImportRefused", "ImportResult", "import_source"]

VERIFY_TIMEOUT = 30


class ImportRefused(ValueError):
    """The source cannot be imported (unknown, no verified licence, licence changed)."""


@dataclass
class ImportResult:
    source: str
    seed: str
    requested: int
    sampled: int
    revision: str
    added: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)


def reference_passes(reference: str, case: dict) -> bool:
    """True when the dataset's reference solution passes the case's tests under
    the code_tests evaluator, the way a model answer would be run."""
    from core.evaluators.code_tests import CodeTestsEvaluator

    score = CodeTestsEvaluator(timeout=VERIFY_TIMEOUT).run_case(
        f"```python\n{reference}\n```", {"tests": case["tests"]}
    )
    return score is not None and score.value == 1.0


def _prepare(src: Source, fx: Fetcher) -> str:
    """Upstream revision; refuses when the card's licence is not the verified one."""
    if src.kind == "git":
        return fx.git_head(src.upstream)
    rev, card = fx.hub_card(src.upstream)
    if src.card_licence and (card or "").lower() != src.card_licence:
        raise ImportRefused(
            f"{src.upstream}: dataset card licence is {card!r}, expected "
            f"{src.card_licence!r}; refusing until it is re-verified")
    return rev


def import_source(
    name: str, into: Path, n: int, seed: str, today: str, *,
    file: str | None = None, dry_run: bool = False,
    fx: Fetcher | None = None, verify=reference_passes,
) -> ImportResult:
    src = SOURCES.get(name)
    if src is None:
        raise ImportRefused(f"unknown source {name!r}; known: {', '.join(sorted(SOURCES))}")
    if src.licence is None or src.stream is None:
        raise ImportRefused(f"{src.upstream}: {src.refusal or 'licence not verified'}")
    if n < 1:
        raise ValueError("--n must be at least 1")
    into = Path(into)
    check(into)  # not append-only / missing: fail before any network use
    fx = fx or Fetcher()
    rev = _prepare(src, fx)
    ctx = Ctx(fx=fx, seed=seed, today=today, rev=rev, verify=verify)
    cases = list(itertools.islice(src.stream(ctx), n))
    added, skipped, problems = add(into, cases, file=file or f"{name}.jsonl", dry_run=dry_run)
    return ImportResult(name, seed, n, len(cases), rev, added, skipped, problems)
