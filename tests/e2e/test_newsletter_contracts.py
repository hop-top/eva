# tests/e2e/test_newsletter_contracts.py
"""End-to-end: 4 newsletter pack contracts run via the standalone CLI dispatch
(`evaluate_contract`), each with a good + bad fixture (T-0201, US-037).

`evaluate_contract` is the function the `eva run --contract` CLI calls and
that the gateway also dispatches through (BUILTIN_EVALUATOR_FACTORIES is the
single source of truth, see core/evaluators/builtin.py). If any of the four
pack contracts route to an unregistered evaluator, the report's `skipped`
list is non-empty and the gate would silent-skip (T-0113). These tests assert
`skipped == []` for all four — that's what closes T-0201.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from cli.run_contract import evaluate_contract


REPO_ROOT = Path(__file__).resolve().parents[2]
PACK_DIR = REPO_ROOT / "contracts" / "newsletter"


# ---------------------------------------------------------------------------
# Pack manifest sanity
# ---------------------------------------------------------------------------

def test_pack_manifest_lists_all_four_contracts():
    manifest = yaml.safe_load((PACK_DIR / "pack.yaml").read_text())
    assert manifest["name"] == "newsletter"
    paths = {item["path"] for item in manifest["contracts"]}
    assert paths == {
        "word-count.yaml",
        "no-hallucinations.yaml",
        "style.yaml",
        "cta-presence.yaml",
    }
    # Every listed file resolves on disk.
    for item in manifest["contracts"]:
        assert (PACK_DIR / item["path"]).exists()


# ---------------------------------------------------------------------------
# word-count
# ---------------------------------------------------------------------------

def test_word_count_pass_short_draft():
    draft = "Short newsletter draft. " * 10  # 30 words
    report = evaluate_contract(PACK_DIR / "word-count.yaml", draft)
    assert report.passed is True
    assert report.skipped == []
    assert report.outcomes[0].name == "word_count"


def test_word_count_fail_over_700():
    draft = "word " * 750
    report = evaluate_contract(PACK_DIR / "word-count.yaml", draft)
    assert report.passed is False
    assert report.skipped == []
    assert "700" in (report.outcomes[0].reason or "")


# ---------------------------------------------------------------------------
# no-hallucinations (v1 weakened — citation marker presence)
# ---------------------------------------------------------------------------

def test_no_hallucinations_pass_with_citation():
    draft = (
        "This week Acme launched a new feature [ref:obj_acme_2026_04].\n\n"
        "Subscribe for more."
    )
    report = evaluate_contract(PACK_DIR / "no-hallucinations.yaml", draft)
    assert report.passed is True
    assert report.skipped == []


def test_no_hallucinations_fail_no_citation():
    draft = "This week Acme raised $50M and the world rejoiced.\n\nReply."
    report = evaluate_contract(PACK_DIR / "no-hallucinations.yaml", draft)
    assert report.passed is False
    assert report.skipped == []


# ---------------------------------------------------------------------------
# style (v1 weakened — tone-token regex)
# ---------------------------------------------------------------------------

def test_style_pass_when_tone_token_present():
    draft = "Hey friends — happy Monday. Big week ahead.\n\nReply."
    report = evaluate_contract(PACK_DIR / "style.yaml", draft)
    assert report.passed is True
    assert report.skipped == []


def test_style_fail_when_tone_tokens_absent():
    draft = (
        "Quarterly performance summary follows. Revenue increased. "
        "Margins compressed. End of report."
    )
    report = evaluate_contract(PACK_DIR / "style.yaml", draft)
    assert report.passed is False
    assert report.skipped == []


# ---------------------------------------------------------------------------
# cta-presence
# ---------------------------------------------------------------------------

def test_cta_presence_pass_with_cta_in_last_paragraph():
    draft = (
        "Big launch this week.\n\n"
        "Three highlights worth your time.\n\n"
        "Reply with your take and forward this to a friend."
    )
    report = evaluate_contract(PACK_DIR / "cta-presence.yaml", draft)
    assert report.passed is True
    assert report.skipped == []


def test_cta_presence_fail_when_last_paragraph_descriptive_only():
    draft = (
        "Reply with your thoughts at the top of the issue.\n\n"
        "Middle body content here.\n\n"
        "And that's the wrap for this week."
    )
    report = evaluate_contract(PACK_DIR / "cta-presence.yaml", draft)
    assert report.passed is False
    assert report.skipped == []


# ---------------------------------------------------------------------------
# T-0113 silent-skip regression: no contract in the pack routes to an
# unknown evaluator. Single parametrised assertion across the four files.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "contract_file",
    [
        "word-count.yaml",
        "no-hallucinations.yaml",
        "style.yaml",
        "cta-presence.yaml",
    ],
)
def test_pack_contract_has_no_skipped_evaluators(contract_file):
    """Closes T-0201: every newsletter pack contract registers at the
    gateway. Empty `skipped` list = pass/fail decision returned, not
    silent-skip.
    """
    # Any non-empty input — we only care that the evaluators *resolve*,
    # not whether they pass.
    report = evaluate_contract(PACK_DIR / contract_file, "placeholder body")
    assert report.skipped == [], (
        f"{contract_file} silent-skipped: {report.skipped}"
    )
