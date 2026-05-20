# core/evaluators/mood.py
"""Tier-1 deterministic mood evaluator (US-038).

Programmatic POS-tag-style detection of writing mood: imperative, past,
passive, or first-person. No LLM. No external deps — uses verb-form lookup
tables + simple sentence segmentation heuristics. Suitable for v1 prose
quality gates where you want to assert e.g. "newsletter intro should NOT be
in past tense" or "tutorial steps SHOULD be imperative".

Configuration:
    expected: one of {"imperative", "past", "passive", "first_person"}.
              The mood the response is asserted to be predominantly in.

Score:
    1.0 if the detected dominant mood matches `expected`, else 0.0 with
    a reason describing the mismatch.
"""
from __future__ import annotations

import re
from collections import Counter

from core.models import Score


# --- verb-form / pronoun tables -------------------------------------------

# Common irregular past-tense verbs. Combined with the regex `\w+ed\b`
# heuristic this catches the bulk of English past-tense usage.
_PAST_IRREGULAR = {
    "was", "were", "had", "did", "said", "made", "went", "took", "came",
    "saw", "got", "gave", "found", "thought", "told", "became", "left",
    "felt", "brought", "began", "kept", "held", "stood", "heard", "let",
    "meant", "set", "met", "ran", "paid", "sat", "spoke", "lay", "led",
    "read", "grew", "lost", "fell", "sent", "built", "spent", "won",
    "wrote", "broke", "drove", "rose", "ate", "drew", "chose", "knew",
    "threw", "flew", "blew", "shook", "swore", "tore", "wore",
}

# Imperative-style sentence-initial verbs (base form). Lowercased — matched
# after .lower() on the first token of a sentence. Far-from-exhaustive
# heuristic, but covers the common tutorial / instructional set.
_IMPERATIVE_LEAD = {
    "open", "click", "run", "install", "create", "add", "remove", "delete",
    "set", "use", "do", "make", "go", "navigate", "select", "choose",
    "type", "enter", "press", "save", "submit", "send", "check", "verify",
    "ensure", "confirm", "review", "read", "look", "find", "search",
    "configure", "build", "compile", "test", "deploy", "import", "export",
    "copy", "paste", "edit", "update", "upgrade", "restart", "stop",
    "start", "enable", "disable", "include", "exclude", "try", "consider",
    "note", "remember", "avoid", "skip", "wait", "follow", "fetch", "pull",
    "push", "commit", "merge", "rebase", "branch", "clone", "fork", "tag",
}

# Pronouns indicating first-person voice.
_FIRST_PERSON_SUBJECT = {"i", "we"}
_FIRST_PERSON_OBJECT = {"me", "us"}
_FIRST_PERSON_POSSESSIVE = {"my", "mine", "our", "ours"}

# Passive auxiliaries — `be`-conjugations.
_BE_FORMS = {"is", "are", "was", "were", "been", "being", "be", "am"}


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_TOKEN_RE = re.compile(r"[A-Za-z']+")
_WORD_RE = re.compile(r"\b\w+\b")


def _sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    # Split on terminal punctuation; also treat newlines as soft breaks so
    # tutorial-style bullet/step lists each count as their own sentence.
    parts: list[str] = []
    for chunk in text.splitlines():
        chunk = chunk.strip()
        if not chunk:
            continue
        # Strip leading list markers `- `, `* `, `1. ` so the verb is the
        # first real token.
        chunk = re.sub(r"^([-*+]\s+|\d+[.)]\s+)", "", chunk)
        for sent in _SENTENCE_SPLIT.split(chunk):
            sent = sent.strip()
            if sent:
                parts.append(sent)
    return parts


def _first_token(sentence: str) -> str | None:
    m = _TOKEN_RE.search(sentence)
    return m.group(0).lower() if m else None


def _is_imperative(sent: str) -> bool:
    """True if sentence starts with a base-form verb (no leading subject)."""
    tok = _first_token(sent)
    if tok is None:
        return False
    if tok in _IMPERATIVE_LEAD:
        return True
    # "Please <verb> ..." also reads as imperative.
    if tok == "please":
        tokens = _TOKEN_RE.findall(sent.lower())
        if len(tokens) >= 2 and tokens[1] in _IMPERATIVE_LEAD:
            return True
    return False


def _has_past(sent: str) -> bool:
    tokens = [t.lower() for t in _WORD_RE.findall(sent)]
    for t in tokens:
        if t in _PAST_IRREGULAR:
            return True
        # Regular -ed past (verbs/participles). Coarse — also catches some
        # adjectives ("interested"), good enough for v1 heuristic.
        if len(t) > 3 and t.endswith("ed") and not t.endswith("ied"):
            return True
        if len(t) > 4 and t.endswith("ied"):
            return True
    return False


def _has_passive(sent: str) -> bool:
    """`be`-form immediately (or near-immediately) followed by a past
    participle. Heuristic: be-form + word ending in -ed/-en within 2 tokens.
    """
    tokens = [t.lower() for t in _WORD_RE.findall(sent)]
    for i, tok in enumerate(tokens):
        if tok in _BE_FORMS:
            for j in range(i + 1, min(i + 4, len(tokens))):
                cand = tokens[j]
                if len(cand) > 3 and (cand.endswith("ed") or cand.endswith("en")):
                    return True
    return False


def _has_first_person(sent: str) -> bool:
    tokens = [t.lower() for t in _WORD_RE.findall(sent)]
    for t in tokens:
        if t in _FIRST_PERSON_SUBJECT or t in _FIRST_PERSON_OBJECT or t in _FIRST_PERSON_POSSESSIVE:
            return True
    return False


_MOODS = ("imperative", "past", "passive", "first_person")


def detect_mood_counts(text: str) -> Counter[str]:
    """Return per-mood sentence counts. A single sentence can match more
    than one mood (e.g. past + passive).
    """
    counts: Counter[str] = Counter()
    for sent in _sentences(text):
        if _is_imperative(sent):
            counts["imperative"] += 1
        if _has_past(sent):
            counts["past"] += 1
        if _has_passive(sent):
            counts["passive"] += 1
        if _has_first_person(sent):
            counts["first_person"] += 1
    return counts


class MoodEvaluator:
    def __init__(self, expected: str):
        if expected not in _MOODS:
            raise ValueError(
                f"expected must be one of {_MOODS}; got {expected!r}"
            )
        self.expected = expected

    def run(self, response: str) -> Score:
        counts = detect_mood_counts(response)
        n_sentences = max(1, len(_sentences(response)))
        expected_n = counts.get(self.expected, 0)
        if expected_n == 0:
            return Score(
                value=0.0,
                reason=(
                    f"no {self.expected} sentences detected "
                    f"(scanned {n_sentences} sentences)"
                ),
            )
        # Dominant = highest-count mood. Ties broken by `expected` winning
        # so a response that's e.g. 1/1 imperative scores pass.
        top = max(_MOODS, key=lambda m: (counts.get(m, 0), m == self.expected))
        if top != self.expected:
            return Score(
                value=0.0,
                reason=(
                    f"dominant mood {top} (n={counts.get(top, 0)}) "
                    f"!= expected {self.expected} (n={expected_n})"
                ),
            )
        return Score(value=1.0)

    _run = run  # deprecated alias; remove in v0.2.0
