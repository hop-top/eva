# core/evaluators/code_block_runs.py
"""Tier-2 deterministic code-block parse evaluator (T-0314, US-043).

Extract fenced code blocks from the response and assert each one parses
in its declared language. Parse-only — no execution. Cheaper than
`code_test_passes` and works for languages where running the snippet is
undesirable.

Per-language strategy (v1):
- python → ast.parse
- json   → json.loads
- yaml   → yaml.safe_load (pyyaml, already a dep)
- sh / bash → subprocess.run(["bash", "-n", ...]) — 5s syntax-check
- anything else → controlled by `unsupported_action` ("skip" or "fail")
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
from typing import Literal

import yaml

from core.models import Score


_FENCE_PATTERN = re.compile(
    r"```([^\s`]*)\s*\n(.*?)```",
    re.DOTALL,
)

UnsupportedAction = Literal["skip", "fail"]


class CodeBlockRunsEvaluator:
    SUPPORTED = {"python", "py", "json", "yaml", "yml", "sh", "bash"}

    def __init__(
        self,
        unsupported_action: UnsupportedAction = "skip",
        require_code_block: bool = False,
    ):
        self.unsupported_action = unsupported_action
        self.require_code_block = require_code_block

    def run(self, response: str) -> Score:
        blocks: list[tuple[str, str]] = []
        for m in _FENCE_PATTERN.finditer(response):
            lang = (m.group(1) or "").strip().lower()
            code = m.group(2)
            blocks.append((lang, code))

        if not blocks:
            if self.require_code_block:
                return Score(
                    value=0.0,
                    reason="no fenced code blocks found",
                )
            return Score(value=1.0)

        for lang, code in blocks:
            if lang in {"python", "py"}:
                err = _check_python(code)
            elif lang == "json":
                err = _check_json(code)
            elif lang in {"yaml", "yml"}:
                err = _check_yaml(code)
            elif lang in {"sh", "bash"}:
                err = _check_bash(code)
            else:
                if self.unsupported_action == "fail":
                    return Score(
                        value=0.0,
                        reason=(
                            f"unsupported language '{lang or 'untagged'}' "
                            f"(unsupported_action=fail)"
                        ),
                    )
                # skip mode: pass-through unsupported blocks
                continue

            if err is not None:
                return Score(
                    value=0.0,
                    reason=f"{lang} parse error: {err}",
                )

        return Score(value=1.0)

    _run = run  # deprecated alias; remove in v0.2.0


def _check_python(code: str) -> str | None:
    try:
        ast.parse(code)
        return None
    except SyntaxError as e:
        return str(e)


def _check_json(code: str) -> str | None:
    try:
        json.loads(code)
        return None
    except json.JSONDecodeError as e:
        return str(e)


def _check_yaml(code: str) -> str | None:
    try:
        yaml.safe_load(code)
        return None
    except yaml.YAMLError as e:
        return str(e)


def _check_bash(code: str) -> str | None:
    try:
        completed = subprocess.run(
            ["bash", "-n"],
            input=code,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except FileNotFoundError:
        return "bash binary not available"
    except subprocess.TimeoutExpired:
        return "bash -n timeout"
    if completed.returncode != 0:
        return (completed.stderr or "").strip()[:500]
    return None
