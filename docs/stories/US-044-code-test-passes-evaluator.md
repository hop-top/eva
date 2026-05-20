# US-044 — code_test_passes Evaluator

**Associated Eva persona:** [Alex — AI Engineer](../personas.md)
**Shared base persona:** [Solo Developer](../../../../../.docs/personas/individuals/solo-developer.md)
**Task:** T-0304, T-0316, T-0317

## Story

As Alex, I want a `code_test_passes` evaluator that extracts a python code block from the
response, appends a configurable test snippet, and runs the combined program in an isolated
subprocess with a timeout, so that I can verify LLM-generated code actually behaves correctly
under canned assertions.

## Context

- Distinct from `code_block_runs` (US-043): this one **executes**. v1 supports python only —
  most reliable cross-platform sandbox via `subprocess.run([sys.executable, "-c", ...])`.
- Sandboxing posture (v1, document limits in story):
  - subprocess isolation with default `timeout=10` seconds (never disable).
  - `shell=False` always — no shell expansion.
  - No PATH inheritance beyond `sys.executable`; env stripped to a minimal allowlist.
  - **Network not blocked at OS level** — caller responsibility to run on offline CI or
    in containers. v1 documents this; v2 may add `seccomp`/`firejail` hooks.
  - No filesystem chroot — code can read/write `/tmp`. Document, do not pretend otherwise.
- Test code provided via `test_code` config string; appended after extracted block separated
  by `\n\n`. Failure = non-zero exit code.

## Acceptance Criteria

- Evaluator extracts the first python fenced code block from the response.
- Evaluator passes (score 1.0) when the combined `extracted_code + "\n\n" + test_code` exits 0
  within the timeout.
- Evaluator fails (score 0.0) with reason "exit code N" when the combined program exits non-zero;
  reason includes a stderr snippet (truncated to ~500 chars).
- Evaluator fails with reason "execution timeout" when `subprocess.run` hits the timeout.
- Evaluator fails with reason "no python code block found" when the response contains no
  python fenced block.
- Evaluator never invokes a shell (`shell=False` always); subprocess args are a list, never a
  string.
- Evaluator's default `timeout` is 10 seconds; constructor accepts an override but `None`
  raises `ValueError` (no infinite-timeout misuse).
- Evaluator captures stdout/stderr but does not raise on non-zero exit — returns a Score.

## Tests

- `tests/e2e/test_code_test_passes_evaluator.py` — one test case per acceptance bullet.

## Limits / Follow-ups

- v1 sandbox limits documented above. v2 candidates: cgroup/firejail wrapping, network egress
  block, tmpfs-only fs, container hand-off.
- Multi-language (node/go/sh execution) deferred — story explicitly python-only.
