---
name: eva-cli
description: Gate AI agent output against behavioral contracts with the eva CLI and gateway. Use when checking an agent response or recorded CLI output against a contract YAML, running an eval dataset as a CI gate, diffing contract versions for regressions, or inspecting stored runs and failures.
---

# eva

eva scores output against a contract's evaluators and reports pass or fail through its exit code. `eva --help` lists every command; `eva <group> --help` lists flags. This file holds what help does not say. `eva skill show` reprints it for the installed version; `eva skill show <reference>` prints a reference file.

## Pick a mode

- **Output already in hand** (agent reply, captured CLI output): `eva run --contract c.yaml --input out.json`. Offline: no agent, no gateway, nothing stored.
- **Live agent, many cases**: `eva run --dataset suite.yaml --no-tui`. Calls the target per test case and stores the run in `.eva/state.db` of the current directory.
- **Gateway** (`eva serve`): other processes gate over HTTP. Read `references/rest-api.md` when you must call or start it.

Write or change a contract first: `references/contract-yaml.md` when you need evaluator names, modes or fields. Then `eva contract validate c.yaml`.

## Gate on exit codes

- `0` all evaluators passed, `1` at least one failed, `2` bad input (missing file, flag combination, no `--dataset`). Never parse text to decide pass or fail.
- `eva contract validate` and `eva contract diff` exit `1` on invalid contracts and regressions. Run `diff` before shipping a contract change.
- Standalone `run --format json` gives one JSON document; it is the default when stdout is not a terminal.
- Standalone `run`: a pass prints its report on stdout, a failure prints it on stderr and leaves stdout empty. Capture both streams.
- Dataset `run`: pass `--no-tui` outside a terminal. It prints `Run: <id>`, an 8-character id for `runs show` and `compare`.

## Escalate when something fails

1. Read the report: each failed evaluator carries a `reason`.
2. `eva failures list --dataset <name>` (also `--evaluator`, `--contract`, `--model`) for stored failures.
3. `eva runs list --status fail`, then `eva runs show --run-id <id>` for the invocations of one run.
4. `eva invocations show --id <uuid>` for scores, usage and artifacts of one invocation.
5. `eva compare --left <baseline-id> --right <new-id>` after a change; `eva drift report --dataset <name> --target <url>` for score trends.

Observe commands read `.eva/state.db` in the current directory. Another file: `--db <path>`. Empty results after standalone runs are expected: they store nothing.

## Human labels

`eva review queue --failed-only` lists failed invocations. `eva annotate add --invocation <uuid> --label correct` records a verdict; confirm the uuid with `invocations show` first.

## Gotchas

- Judge evaluators (`relevance`, `tone`, `safety`, ...) need a judge model (`EVA_JUDGE_MODEL`) and, in standalone mode, `--prompt` or `--prompt-file`. Without them they are skipped, listed under `skipped_judge`, and the exit code is unaffected: a skipped judge is not a pass.
- `--contract` with `--input`: both or neither. They cannot be mixed with `--dataset` or `--target`; `--target` cannot be mixed with `--provider`, `--base-url` or `--model`.
- `eva init` scaffolds `evals/`, `plugins.py`, `.env` and `eva.yaml` in the current directory; skip it when they exist.
- `--no-auth` on `eva serve` opens every route to anyone who can reach the port. Use it for local work only, with `--host 127.0.0.1`.
- Keep API keys out of command lines: `--api-key-env` takes the name of an environment variable, not the key.
