# core/evaluators/code_tests.py
"""``code_tests``: execute model-generated code against per-case unit tests.

SECURITY: this EXECUTES MODEL OUTPUT on the host in a contained subprocess
(see ``core/evaluators/_sandbox.py`` and ``isolation_status()``). It is
hardening, not a guarantee; run untrusted workloads inside a container or VM.

Always: temp working dir (deleted afterwards, ``HOME``/``TMPDIR`` point into
it), ``python -I``, minimal env (no inherited secrets), stdin closed, own
process group killed on exit, wall-clock timeout, CPU-time / file-size /
core-dump rlimits, parent-side resident-memory and process-count cap.
macOS adds a ``sandbox-exec`` profile: no network, no fork, no writes
outside the temp dir, no file reads under /Users, /Volumes and temp roots.
Linux adds a network namespace when unprivileged user namespaces are allowed.
NOT contained on Linux: filesystem reads and writes outside the temp dir.

Flow: take the last fenced block for the language (tag match first, then
last untagged block), append the case's tests, run. Exit 0 = 1.0, else
0.0 with the failure reason (timeout / exit code + stderr tail).

stdin/stdout mode: a case with ``stdio`` (list of ``{stdin, expected_stdout}``)
runs the extracted program once per pair (fresh temp dir each, ``timeout`` per
run) and compares stdout after trailing-whitespace normalisation. Score is
all-or-nothing unless ``partial`` is set; the reason carries ``passed N/M``.

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
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass

from core.chat_targets import split_reasoning
from core.evaluators import _sandbox
from core.models import Score

_FENCE = re.compile(r"```[ \t]*([^\s`]*)[^\n`]*\n(.*?)```", re.DOTALL)
_OUTPUT_LIMIT = 4000
_MAX_LISTED_FAILURES = 3


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


def _normalise(s: str) -> str:
    """Trailing whitespace on each line and at the end is not significant."""
    lines = (s or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(line.rstrip() for line in lines).rstrip()


def _clip(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n] + "..."


def _tail(s: str, n: int = 500) -> str:
    s = (s or "").strip()
    return s[-n:]


class CodeTestsEvaluator:
    """Run the response's last code block plus the case's tests."""

    def __init__(
        self,
        language: str = "python",
        timeout: float = 10,
        test_code: str = "",
        memory_mb: int = 512,
        max_file_mb: int = 16,
        partial: bool = False,
        require_isolation: bool = False,
    ):
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
        self.memory_mb = memory_mb
        self.max_file_mb = max_file_mb
        self.partial = partial
        self.require_isolation = require_isolation

    def run(self, response: str) -> Score:
        # No case context: only the shared ``test_code`` config can supply tests.
        return self.run_case(response, {}) or Score(
            value=0.0, reason="no tests: set test_code or score via a dataset case"
        )

    def run_case(self, response: str, case: dict) -> Score | None:
        """Score one case; ``None`` = not applicable (case carries no tests)."""
        stdio = case.get("stdio")
        has_work = bool(stdio) or bool(
            "\n".join(
                t for t in (_tests_text(case.get("tests")), self.test_code) if t
            ).strip()
        )
        if has_work and (missing := self._isolation_missing()):
            return Score(value=0.0, reason=missing)
        if stdio:
            if _tests_text(case.get("tests")).strip():
                return Score(
                    value=0.0,
                    reason="case has both tests and stdio; give one",
                )
            return self._run_stdio(response, stdio)
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

    def _isolation_missing(self) -> str | None:
        """With ``require_isolation``: reason when no OS-level layer is active."""
        if not self.require_isolation:
            return None
        st = _sandbox.isolation_status()
        if st.get("mechanism", "none") != "none":
            return None
        lacking = ", ".join(k for k, v in st.items() if k != "mechanism" and not v)
        return (
            "require_isolation set but no OS-level isolation is available "
            f"(mechanism: none; not active: {lacking}); program not run"
        )

    def _run(self, workdir: str, stdin_data: str | None = None) -> _sandbox.RunResult:
        return _sandbox.run_isolated(
            self.language.command(self.language.filename),
            workdir=workdir,
            timeout=self.timeout,
            stdin_data=stdin_data,
            memory_mb=self.memory_mb,
            max_file_mb=self.max_file_mb,
        )

    def _failure(self, r: _sandbox.RunResult) -> str:
        """Human-readable reason for a non-zero / killed run."""
        if r.killed == "timeout":
            return f"execution timeout after {self.timeout}s"
        if r.killed == "memory":
            return f"memory limit exceeded (>{self.memory_mb} MB)"
        if r.killed == "processes":
            return "process limit exceeded"
        if r.returncode == -signal.SIGXFSZ or "File too large" in (r.stderr or ""):
            return f"file size limit exceeded (>{self.max_file_mb} MB)"
        if r.returncode == -signal.SIGXCPU:
            return "cpu time limit exceeded"
        detail = _tail((r.stderr or r.stdout)[-_OUTPUT_LIMIT:])
        reason = f"exit code {r.returncode}"
        if detail:
            reason += f": {detail}"
        if r.contained and "Operation not permitted" in (r.stderr or ""):
            reason += " (blocked by sandbox)"
        return reason

    def _run_stdio(self, response: str, stdio: list) -> Score:
        pairs: list[tuple[str, str]] = []
        for i, p in enumerate(stdio, 1):
            if not isinstance(p, dict) or not isinstance(p.get("expected_stdout"), str):
                return Score(
                    value=0.0, reason=f"stdio pair {i}: expected_stdout (string) required"
                )
            stdin = p.get("stdin", "")
            if not isinstance(stdin, str):
                return Score(value=0.0, reason=f"stdio pair {i}: stdin must be a string")
            pairs.append((stdin, p["expected_stdout"]))
        answer, _ = split_reasoning(response)
        code = extract_last_block(answer, self.language)
        if code is None:
            return Score(value=0.0, reason=f"no {self.language.name} code block found")
        passed = 0
        failures: list[str] = []
        for i, (stdin, expected) in enumerate(pairs, 1):
            outcome = self._run_pair(code, stdin, expected)
            if outcome is None:
                passed += 1
            else:
                failures.append(f"test {i}: {outcome}")
        total = len(pairs)
        reason = f"passed {passed}/{total}"
        if failures:
            reason += "; " + "; ".join(failures[:_MAX_LISTED_FAILURES])
            if len(failures) > _MAX_LISTED_FAILURES:
                reason += f"; +{len(failures) - _MAX_LISTED_FAILURES} more"
        if passed == total:
            value = 1.0
        else:
            value = passed / total if self.partial else 0.0
        return Score(value=value, reason=reason)

    def _run_pair(self, code: str, stdin: str, expected: str) -> str | None:
        """``None`` = pass; else a short failure description."""
        workdir = tempfile.mkdtemp(prefix="eva-code-")
        try:
            with open(os.path.join(workdir, self.language.filename), "w") as f:
                f.write(code + "\n")
            r = self._run(workdir, stdin_data=stdin)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        if r.killed is not None or r.returncode != 0:
            msg = self._failure(r)
            if r.killed is None and msg.startswith("exit code"):
                msg = "runtime error (" + msg[0].lower() + msg[1:] + ")"
            return _clip(msg, 300)
        if _normalise(r.stdout) == _normalise(expected):
            return None
        return (
            f"wrong output (expected {_clip(_normalise(expected), 80)!r}, "
            f"got {_clip(_normalise(r.stdout), 80)!r})"
        )

    def _execute(self, program: str) -> Score:
        workdir = tempfile.mkdtemp(prefix="eva-code-")
        try:
            with open(os.path.join(workdir, self.language.filename), "w") as f:
                f.write(program)
            r = self._run(workdir)
            if r.killed is None and r.returncode == 0:
                return Score(value=1.0)
            return Score(value=0.0, reason=self._failure(r))
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
