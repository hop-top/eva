# tests/e2e/test_citation_evaluator.py
"""E2E tests: citation / grounding evaluator (T-0313, US-042).

One test case per acceptance bullet in docs/stories/US-042-citation-evaluator.md.
"""
from __future__ import annotations

from core.evaluators.citation import CitationEvaluator
from core.models import Score


# AC1: passes on zero markers when require_citation=False (default).
def test_passes_when_no_markers_and_not_required():
    ev = CitationEvaluator(allowed_sources={"obj_a"})
    score = ev.run("Just a plain response with no markers.")
    assert isinstance(score, Score)
    assert score.value == 1.0


# AC2: every [ref:<id>] marker resolves to allowed_sources.
def test_passes_when_every_ref_marker_in_allowed_set():
    ev = CitationEvaluator(allowed_sources={"obj_a", "obj_b"})
    score = ev.run("First [ref:obj_a] and second [ref:obj_b] both grounded.")
    assert score.value == 1.0


# AC3: every URL marker present in allowed_sources (exact match).
def test_passes_when_every_url_in_allowed_set():
    ev = CitationEvaluator(allowed_sources={"https://example.com/a"})
    score = ev.run("See https://example.com/a for details.")
    assert score.value == 1.0


# AC4: ref marker not in allowed -> fail naming offending id.
def test_fails_on_unknown_ref_id():
    ev = CitationEvaluator(allowed_sources={"obj_a"})
    score = ev.run("Claim with [ref:obj_unknown] marker.")
    assert score.value == 0.0
    assert "obj_unknown" in (score.reason or "")


# AC5: URL marker not in allowed -> fail naming the URL.
def test_fails_on_unknown_url():
    ev = CitationEvaluator(allowed_sources={"https://example.com/a"})
    score = ev.run("See https://evil.example.com/x for more.")
    assert score.value == 0.0
    assert "evil.example.com" in (score.reason or "")


# AC6: require_citation=True and zero markers -> fail.
def test_fails_when_required_and_no_markers():
    ev = CitationEvaluator(allowed_sources={"obj_a"}, require_citation=True)
    score = ev.run("No markers here at all.")
    assert score.value == 0.0
    assert "no citation markers" in (score.reason or "").lower()


# AC7: multiple markers, first offender reported (left-to-right).
def test_first_offender_reported_in_mixed_markers():
    ev = CitationEvaluator(allowed_sources={"obj_a"})
    score = ev.run("Good [ref:obj_a] then bad [ref:obj_bad] then worse [ref:obj_evil].")
    assert score.value == 0.0
    assert "obj_bad" in (score.reason or "")
    assert "obj_evil" not in (score.reason or "")


# AC8: pure-Python, no I/O — large input completes near-instantly.
def test_handles_large_input_without_io():
    # 50 KB of plain text with one good marker.
    body = ("Lorem ipsum dolor sit amet. " * 2000) + " [ref:obj_a]"
    ev = CitationEvaluator(allowed_sources={"obj_a"})
    score = ev.run(body)
    assert score.value == 1.0


# Regression: duplicate markers must order by FIRST occurrence, not collapse
# to a single offset. Previously the sort key called ``response.find(...)``
# which returned the leftmost offset for every duplicate, breaking the
# "first offender reported left-to-right" guarantee from AC7.
def test_duplicate_offending_markers_ordered_by_occurrence():
    ev = CitationEvaluator(allowed_sources={"obj_a"})
    # Good marker comes first; the FIRST bad marker (obj_bad) sits before
    # the second bad marker. obj_bad appears twice; the second copy must
    # not pre-empt obj_worse just because find() returns the leftmost
    # offset for both instances of obj_bad.
    response = (
        "Start [ref:obj_a] then [ref:obj_bad] middle [ref:obj_worse] "
        "and again [ref:obj_bad] end."
    )
    score = ev.run(response)
    assert score.value == 0.0
    # The first offender by scan order is obj_bad, NOT obj_worse.
    assert "obj_bad" in (score.reason or "")
    assert "obj_worse" not in (score.reason or "")


def test_duplicate_offending_urls_ordered_by_occurrence():
    ev = CitationEvaluator(allowed_sources={"https://good.example/a"})
    response = (
        "First https://bad.example/x then "
        "https://worse.example/y then again "
        "https://bad.example/x at the end."
    )
    score = ev.run(response)
    assert score.value == 0.0
    # First scan-order offender is bad.example/x, not worse.example/y.
    assert "bad.example" in (score.reason or "")
    assert "worse.example" not in (score.reason or "")
