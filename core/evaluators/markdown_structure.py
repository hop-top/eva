# core/evaluators/markdown_structure.py
"""Tier-2 deterministic markdown structure evaluator (T-0320, US-046).

Assert the response satisfies a configurable structural contract:
- Required H2 sections present (exact stripped-text match).
- Required fenced code-block languages present.
- No broken local links (empty href or malformed `./../` style targets).

v1 uses a stdlib regex scanner. No markdown parser dep. Limitations:
- HTML-block edge cases not handled.
- Tab-indented code fences not detected (markdown spec is ATX fences only).
- "Broken local link" is operationalised as empty target or `./../` malformed
  paths — no filesystem existence checking. Documented in story.
"""
from __future__ import annotations

import re

from core.models import Score


_H_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_FENCE_PATTERN = re.compile(r"```([^\s`]*)\s*\n", re.MULTILINE)
_LINK_PATTERN = re.compile(r"(?<!\!)\[([^\]]*)\]\(([^\)]*)\)")


class MarkdownStructureEvaluator:
    def __init__(
        self,
        required_h2: list[str] | None = None,
        required_code_langs: list[str] | None = None,
        disallow_broken_local_links: bool = False,
    ):
        self.required_h2 = list(required_h2 or [])
        self.required_code_langs = [
            lang.lower() for lang in (required_code_langs or [])
        ]
        self.disallow_broken_local_links = disallow_broken_local_links

    def run(self, response: str) -> Score:
        if not response.strip():
            return Score(value=0.0, reason="empty response")

        h2_titles = {
            text.strip()
            for hashes, text in _H_PATTERN.findall(response)
            if len(hashes) == 2
        }
        for required in self.required_h2:
            if required not in h2_titles:
                return Score(
                    value=0.0,
                    reason=f"missing H2 section: '{required}'",
                )

        fence_langs = {lang.strip().lower() for lang in _FENCE_PATTERN.findall(response)}
        for required in self.required_code_langs:
            if required not in fence_langs:
                return Score(
                    value=0.0,
                    reason=f"missing code block for language: '{required}'",
                )

        if self.disallow_broken_local_links:
            for _text, href in _LINK_PATTERN.findall(response):
                if _is_broken_local_link(href):
                    return Score(
                        value=0.0,
                        reason=f"broken local link: '{href}'",
                    )

        return Score(value=1.0)

    _run = run  # deprecated alias; remove in v0.2.0


def _is_broken_local_link(href: str) -> bool:
    stripped = href.strip()
    if not stripped:
        return True
    # External or anchor or mail links are not "local" in our sense.
    lowered = stripped.lower()
    if lowered.startswith(("http://", "https://", "mailto:", "#", "ftp://")):
        return False
    # Heuristic broken-pattern: contains a `..` segment without a clean
    # extension OR contains repeated `./.` style noise.
    if re.search(r"\.\./?\.\./?\.\.", stripped):
        return True
    if stripped.endswith("/.."):
        return True
    return False
