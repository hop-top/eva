# core/evaluators/language.py
"""Tier-1 deterministic language evaluator (US-039).

Asserts the response is in an expected natural language. `langdetect` is NOT
a project dependency in v1; we use a stdlib-only heuristic combining
character-set signals (Latin / Cyrillic / CJK / Arabic / Hebrew / Greek) and
common-word stoplists for English, French, Spanish, German, Italian, and
Portuguese. Good enough for unambiguous prose; non-Latin scripts are
detected by Unicode block.

Configuration:
    expected: ISO-639-1 code of the asserted language (e.g. "en", "fr").
              The full supported set is `SUPPORTED_LANGUAGES`.

Score:
    1.0 if detected language matches `expected`, else 0.0 with a reason
    naming the detected language.
"""
from __future__ import annotations

import re
import unicodedata

from core.models import Score


# --- common-word stoplists (low-frequency words removed; tuned for short
# samples). Lowercased. Latin-script langs only — non-Latin handled by
# script detection up front.

_STOPLISTS: dict[str, set[str]] = {
    "en": {
        "the", "and", "of", "to", "a", "in", "is", "it", "you", "that",
        "he", "was", "for", "on", "are", "with", "as", "i", "his", "they",
        "be", "at", "one", "have", "this", "from", "or", "had", "by", "but",
        "not", "what", "all", "we", "when", "your", "can", "said", "there",
        "use", "an", "each", "which", "she", "do", "how", "their", "if",
        "will", "up", "other", "about", "out", "many", "then", "them",
        "these", "so", "some", "her", "would", "make", "like", "into",
        "him", "has", "two", "more", "very", "after", "our", "just",
    },
    "fr": {
        "le", "la", "les", "de", "et", "à", "un", "une", "des", "est",
        "que", "pour", "dans", "ce", "il", "qui", "ne", "sur", "se", "pas",
        "plus", "par", "avec", "tout", "comme", "mais", "ou", "où", "son",
        "sa", "ses", "ces", "cette", "cet", "nous", "vous", "ils", "elles",
        "avoir", "être", "faire", "dire", "aussi", "très", "bien", "fait",
        "leur", "leurs", "déjà", "encore", "donc", "alors", "même",
        "elle", "lui", "moi", "toi", "soi", "y", "en", "n'est", "c'est",
        "j'ai", "d'un", "d'une", "l'a", "n'a",
    },
    "es": {
        "el", "la", "los", "las", "de", "y", "a", "que", "en", "un",
        "una", "se", "es", "por", "para", "con", "no", "su", "sus", "lo",
        "le", "les", "como", "más", "pero", "sus", "ya", "muy", "fue",
        "ser", "estar", "haber", "todo", "todos", "este", "esta", "estos",
        "estas", "ese", "esa", "esos", "esas", "nosotros", "vosotros",
        "ellos", "ellas", "él", "yo", "tú", "usted", "también", "porque",
        "cuando", "donde", "qué", "cuál", "quién", "hasta", "desde",
    },
    "de": {
        "der", "die", "das", "und", "ist", "in", "zu", "den", "von", "mit",
        "sich", "auf", "für", "im", "dem", "nicht", "ein", "eine", "auch",
        "es", "an", "werden", "aus", "er", "sie", "wir", "ihr", "ihre",
        "sein", "haben", "wird", "kann", "noch", "nur", "war", "wenn",
        "aber", "oder", "als", "bei", "nach", "über", "durch", "unter",
        "vor", "zwischen", "ohne", "gegen", "schon", "sehr", "mehr",
    },
    "it": {
        "il", "la", "i", "le", "di", "che", "e", "a", "un", "una",
        "in", "per", "con", "non", "è", "del", "della", "dei", "delle",
        "al", "alla", "agli", "alle", "si", "se", "ma", "anche", "come",
        "più", "molto", "questo", "questa", "questi", "queste", "quello",
        "essere", "avere", "fare", "sono", "ho", "ha", "abbiamo", "hanno",
        "noi", "voi", "loro", "lui", "lei", "io", "tu", "perché", "quando",
    },
    "pt": {
        "o", "a", "os", "as", "de", "do", "da", "dos", "das", "e",
        "em", "um", "uma", "que", "para", "por", "com", "não", "se",
        "no", "na", "nos", "nas", "ao", "à", "aos", "às", "mais", "como",
        "mas", "também", "muito", "ser", "estar", "ter", "haver", "este",
        "esta", "estes", "estas", "esse", "essa", "esses", "essas",
        "nós", "vós", "eles", "elas", "ele", "ela", "eu", "tu", "você",
    },
}

SUPPORTED_LANGUAGES: tuple[str, ...] = tuple(_STOPLISTS.keys()) + (
    "ja", "zh", "ru", "ar", "he", "el",
)


# --- script detection -----------------------------------------------------

def _script_signal(text: str) -> str | None:
    """Return an ISO-639-1 hint if the text is dominantly non-Latin script.
    Returns None for Latin / ambiguous text — defer to stoplist matching.
    """
    counts: dict[str, int] = {}
    for ch in text:
        if not ch.isalpha():
            continue
        try:
            name = unicodedata.name(ch)
        except ValueError:
            continue
        if name.startswith("CJK UNIFIED IDEOGRAPH") or name.startswith("HIRAGANA") or name.startswith("KATAKANA"):
            # Hiragana / Katakana → Japanese; bare Han → Chinese (best-effort).
            if name.startswith("HIRAGANA") or name.startswith("KATAKANA"):
                counts["ja"] = counts.get("ja", 0) + 1
            else:
                counts["zh"] = counts.get("zh", 0) + 1
        elif name.startswith("CYRILLIC"):
            counts["ru"] = counts.get("ru", 0) + 1
        elif name.startswith("ARABIC"):
            counts["ar"] = counts.get("ar", 0) + 1
        elif name.startswith("HEBREW"):
            counts["he"] = counts.get("he", 0) + 1
        elif name.startswith("GREEK"):
            counts["el"] = counts.get("el", 0) + 1
    if not counts:
        return None
    top, n = max(counts.items(), key=lambda kv: kv[1])
    total_alpha = sum(1 for ch in text if ch.isalpha())
    if total_alpha and n / total_alpha >= 0.30:
        # Japanese: if kana present at all, prefer ja over zh.
        if "ja" in counts and counts["ja"] > 0:
            return "ja"
        return top
    return None


_WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]+", re.UNICODE)


def detect_language(text: str) -> str | None:
    """Best-effort language detection. Returns ISO-639-1 code or None if
    ambiguous (empty / single word / no stoplist hits).
    """
    if not text or not text.strip():
        return None
    script = _script_signal(text)
    if script is not None:
        return script
    tokens = [t.lower() for t in _WORD_RE.findall(text)]
    if len(tokens) < 1:
        return None
    scores: dict[str, int] = {lang: 0 for lang in _STOPLISTS}
    for tok in tokens:
        for lang, stops in _STOPLISTS.items():
            if tok in stops:
                scores[lang] += 1
    top_lang, top_score = max(scores.items(), key=lambda kv: kv[1])
    if top_score == 0:
        return None
    # Require margin to call mixed input ambiguous.
    sorted_scores = sorted(scores.values(), reverse=True)
    if len(sorted_scores) >= 2 and sorted_scores[0] == sorted_scores[1]:
        return None
    return top_lang


class LanguageEvaluator:
    def __init__(self, expected: str):
        if expected not in SUPPORTED_LANGUAGES:
            raise ValueError(
                f"expected must be one of {SUPPORTED_LANGUAGES}; got {expected!r}"
            )
        self.expected = expected

    def run(self, response: str) -> Score:
        detected = detect_language(response)
        if detected is None:
            return Score(
                value=0.0,
                reason=f"could not detect language (expected {self.expected})",
            )
        if detected != self.expected:
            return Score(
                value=0.0,
                reason=f"detected language {detected!r} != expected {self.expected!r}",
            )
        return Score(value=1.0)

    _run = run  # deprecated alias; remove in v0.2.0
