# core/evaluators/code_test_passes.py
"""Tier-2 code-execution evaluator (T-0316, US-044).

Extract the first python fenced code block from the response, append a
configured test snippet, and execute the combined program in a subprocess
with a strict timeout. Exit 0 = pass.

Sandbox posture (v1):
- subprocess isolation with default timeout=10 seconds (never disable).
- shell=False always — no shell expansion of user code.
- Minimal env (PATH-only) — no inherited secrets.
- Network NOT blocked at OS level (document, do not pretend).
- Filesystem NOT chrooted (document).

Multi-language deferred — v1 python only. v2 candidates: node/go/sh
under cgroup or firejail wrapping.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

from core.models import Score


_PY_FENCE = re.compile(
    r"```(?:python|py)\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)


class CodeTestPassesEvaluator:
    def __init__(self, test_code: str = "", timeout: int = 10):
        if timeout is None:
            raise ValueError(
                "timeout=None is not permitted — set an integer second limit"
            )
        self.test_code = test_code
        self.timeout = timeout

    def run(self, response: str) -> Score:
        m = _PY_FENCE.search(response)
        if not m:
            return Score(
                value=0.0,
                reason="no python code block found",
            )
        extracted = m.group(1)
        program = extracted + "\n\n" + self.test_code

        # Minimal env — PATH-only — strip secrets from caller env.
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}

        try:
            completed = subprocess.run(
                [sys.executable, "-c", program],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                shell=False,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return Score(
                value=0.0,
                reason=f"execution timeout after {self.timeout}s",
            )

        if completed.returncode == 0:
            return Score(value=1.0)

        stderr_snippet = (completed.stderr or "").strip()[:500]
        return Score(
            value=0.0,
            reason=(
                f"exit code {completed.returncode}: {stderr_snippet}"
                if stderr_snippet
                else f"exit code {completed.returncode}"
            ),
        )

    _run = run  # deprecated alias; remove in v0.2.0
