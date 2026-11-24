# core/evaluators/code_tests.py
"""``code_tests``: execute model-generated code against per-case unit tests.

SECURITY: this EXECUTES MODEL OUTPUT on the host. Use it only on trusted
runs and inside a sandbox you control (container, VM, throwaway user).
Isolation here is best-effort hygiene, not a security boundary:

- temp working dir, deleted afterwards; ``HOME`` points into it
- ``python -I`` (isolated: no user site, no PYTHON* env, no cwd on path)
- minimal env (PATH only + a few fixed vars) — no inherited secrets
- stdin closed, output truncated, hard wall-clock timeout, process group
  killed on timeout
- NOT blocked: network, filesystem access outside the temp dir, CPU/RAM

Flow: take the last fenced block for the language (tag match first, then
last untagged block), append the case's tests, run. Exit 0 = 1.0, else
0.0 with the failure reason (timeout / exit code + stderr tail).

Per-case test code comes from the test case's ``tests`` field (string or
list of strings, joined by newlines); the evaluator's ``test_code`` config
is appended after it as a shared harness. A case with neither is not
applicable: the evaluator yields no result for it (so one dataset can mix
code cases and answer cases).

Language extension: add a ``CodeLanguage`` to ``CODE_LANGUAGES``.
"""
from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass

from core.chat_targets import split_reasoning
from core.models import Score

_FENCE = re.compile(r"```[ \t]*([^\s`]*)[^\n`]*\n(.*?)```", re.DOTALL)
_OUTPUT_LIMIT = 4000


@dataclass(frozen=True)
class CodeLanguage:
    name: str
    tags: frozenset[str]  # fence info-string tags that select this language
    filename: str
    command: Callable[[str], list[str]]  # filename -> argv


CODE_LANGUAGES: dict[str, CodeLanguage] = {
    "python": CodeLanguage(
        name="python",
        tags=frozenset({"python", "py", "python3"}),
        filename="main.py",
        command=lambda f: [sys.executable, "-I", f],
    ),
}


def extract_last_block(text: str, lang: CodeLanguage) -> str | None:
    """Last fenced block tagged for ``lang``; else last untagged block."""
    tagged: str | None = None
    untagged: str | None = None
    for m in _FENCE.finditer(text):
        tag = m.group(1).lower()
        if tag in lang.tags:
            tagged = m.group(2)
        elif not tag:
            untagged = m.group(2)
    return tagged if tagged is not None else untagged


def _tests_text(tests: str | list[str] | None) -> str:
    if tests is None:
        return ""
    if isinstance(tests, str):
        return tests
    return "\n".join(tests)


def _tail(s: str, n: int = 500) -> str:
    s = (s or "").strip()
    return s[-n:]


class CodeTestsEvaluator:
    """Run the response's last code block plus the case's tests."""

    def __init__(self, language: str = "python", timeout: float = 10, test_code: str = ""):
        if timeout is None:
            raise ValueError("timeout=None is not permitted — set a second limit")
        if language not in CODE_LANGUAGES:
            raise ValueError(
                f"unsupported language {language!r}; "
                f"supported: {', '.join(sorted(CODE_LANGUAGES))}"
            )
        self.language = CODE_LANGUAGES[language]
        self.timeout = timeout
        self.test_code = test_code

    def run(self, response: str) -> Score:
        # No case context: only the shared ``test_code`` config can supply tests.
        return self.run_case(response, {}) or Score(
            value=0.0, reason="no tests: set test_code or score via a dataset case"
        )

    def run_case(self, response: str, case: dict) -> Score | None:
        """Score one case; ``None`` = not applicable (case carries no tests)."""
        tests = "\n".join(
            t for t in (_tests_text(case.get("tests")), self.test_code) if t
        )
        if not tests.strip():
            return None
        answer, _ = split_reasoning(response)
        code = extract_last_block(answer, self.language)
        if code is None:
            return Score(
                value=0.0, reason=f"no {self.language.name} code block found"
            )
        return self._execute(code + "\n\n" + tests + "\n")

    def _execute(self, program: str) -> Score:
        workdir = tempfile.mkdtemp(prefix="eva-code-")
        try:
            with open(os.path.join(workdir, self.language.filename), "w") as f:
                f.write(program)
            env = {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "HOME": workdir,
                "TMPDIR": workdir,
                "LANG": "C.UTF-8",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            proc = subprocess.Popen(
                self.language.command(self.language.filename),
                cwd=workdir,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                errors="replace",
                start_new_session=True,
            )
            try:
                out, err = proc.communicate(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.communicate()
                return Score(
                    value=0.0, reason=f"execution timeout after {self.timeout}s"
                )
            if proc.returncode == 0:
                return Score(value=1.0)
            detail = _tail((err or out)[-_OUTPUT_LIMIT:])
            return Score(
                value=0.0,
                reason=f"exit code {proc.returncode}: {detail}"
                if detail
                else f"exit code {proc.returncode}",
            )
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
