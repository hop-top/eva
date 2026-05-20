# core/evaluators/sentence_paragraph_count.py
"""Tier-2 deterministic structural counter evaluator (T-0322, US-047).

One class, two modes via `mode: "sentence" | "paragraph"`. Both report a
single integer count compared against `min`/`max` bounds (same gate
semantics as `word_count`).

Sentence segmentation:
- Stdlib regex split on `[.?!]+\\s+` after masking a small abbreviation
  allowlist (Mr., Dr., e.g., etc.).
- Bullet list items (`-`, `*`, `+`, `N.` prefix) count as one sentence
  each, regardless of terminal punctuation.

Paragraph segmentation:
- Blocks separated by blank lines (re-uses the convention from
  `last_paragraph_regex`).
- A contiguous run of `> ` blockquote lines is treated as one paragraph.

v2 candidates (deferred): full sentence tokeniser via nltk or spacy.
"""
from __future__ import annotations

import re
from typing import Literal

from core.models import Score


Mode = Literal["sentence", "paragraph"]

_ABBREVIATIONS = (
    "Mr.", "Mrs.", "Ms.", "Dr.", "Prof.", "Sr.", "Jr.",
    "St.", "vs.", "e.g.", "i.e.", "etc.",
)
_ABBREV_MASK = "\x00ABBR\x00"

_BULLET_LINE = re.compile(r"^\s*([-*+]|\d+\.)\s+\S", re.MULTILINE)


class SentenceParagraphCountEvaluator:
    def __init__(
        self,
        mode: Mode = "sentence",
        min: int | None = None,
        max: int | None = None,
    ):
        if mode not in {"sentence", "paragraph"}:
            raise ValueError(f"mode must be 'sentence' or 'paragraph', got {mode}")
        self.mode = mode
        self.min = min
        self.max = max

    def run(self, response: str) -> Score:
        if self.mode == "sentence":
            count = _count_sentences(response)
            label = "sentence"
        else:
            count = _count_paragraphs(response)
            label = "paragraph"

        if self.min is not None and count < self.min:
            return Score(
                value=0.0,
                reason=f"{label} count {count} < {self.min} (min)",
            )
        if self.max is not None and count > self.max:
            return Score(
                value=0.0,
                reason=f"{label} count {count} > {self.max} (max)",
            )
        return Score(value=1.0)

    _run = run  # deprecated alias; remove in v0.2.0


def _count_sentences(text: str) -> int:
    if not text.strip():
        return 0

    # Bullet items count as one each; pull them out before sentence split
    # so terminal punctuation inside a bullet doesn't double-count.
    bullets = _BULLET_LINE.findall(text)
    bullet_count = len(bullets)

    # Strip bullet lines from the text used for sentence-splitting.
    non_bullet = "\n".join(
        line for line in text.splitlines()
        if not _BULLET_LINE.match(line)
    )

    # Mask abbreviations so the split doesn't fire mid-token.
    masked = non_bullet
    for abbr in _ABBREVIATIONS:
        masked = masked.replace(abbr, abbr.replace(".", _ABBREV_MASK))

    # Split on terminal punctuation followed by whitespace OR end-of-string.
    parts = re.split(r"[.!?]+(?:\s+|$)", masked.strip())
    prose_sentences = [p for p in parts if p.strip()]
    return len(prose_sentences) + bullet_count


def _count_paragraphs(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0

    raw_blocks = re.split(r"\n\s*\n", stripped)
    count = 0
    for block in raw_blocks:
        if block.strip():
            count += 1
    return count
