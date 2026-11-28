---
name: eva-cli
description: Gate AI agent output against behavioral contracts and benchmark models with the eva CLI and gateway. Use when checking an agent reply or recorded CLI output against a contract YAML, running an eval dataset as a CI gate, benchmarking chat models on a dataset that only grows, diffing contract versions for regressions, or inspecting stored runs, results and failures.
---

# eva

eva scores output against a contract's evaluators and reports the verdict through its exit code. `eva --help` lists every command; `eva <group> --help` lists flags. This file holds what help does not say. `eva skill show` reprints it for the installed version; `eva skill show <reference>` prints a reference file.

## Pick a path

- **Output already in hand** (agent reply, captured CLI output): `eva run --contract c.yaml --input out.json`. Offline: no agent, no gateway, nothing stored.
- **Live agent, many cases**: `eva run --dataset suite.yaml --no-tui`. Calls the target per case and stores the run in `.eva/state.db` of the current directory.
- **Benchmark models over time**: a dataset that only grows, each model run once per case. Read `references/benchmarks.md` before building or running one.
- **Gateway** (`eva serve`): other processes gate over HTTP. Read `references/rest-api.md` when you start it or call it.

Writing or changing a contract: read `references/contract-yaml.md` for evaluator names and fields, then `eva contract validate c.yaml`.

## Gate on exit codes

- `0` every evaluator passed, `1` at least one failed, `2` bad input. Decide pass or fail from the exit code alone.
- `2` with `evaluator 'X': ...` on stderr names the evaluator and the config key to fix; nothing ran.
- `eva contract validate` and `eva contract diff` exit `1` on an invalid contract or a regression. Run `diff` before shipping a contract change.
- Standalone `run`: `--format json` is the default when stdout is not a terminal. A pass prints the report on stdout; a failure prints it on stderr and leaves stdout empty, so capture both streams.
- Dataset `run`: pass `--no-tui` outside a terminal. It prints `Run: <id>` for `runs show` and `compare`.

## Escalate when something fails

Stop at the first step that names the failing evaluator and its reason.

1. Read the report: each failed evaluator carries a `reason`.
2. `eva failures list --dataset <name>` (also `--evaluator`, `--contract`, `--model`) for stored failures.
3. `eva runs list --status fail`, then `eva runs show --run-id <id> --format json` for one run's cases and invocations.
4. `eva invocations show --id <uuid>` for scores, usage and artifacts of one invocation.
5. `eva compare --left <baseline-id> --right <new-id>` after a change; `eva drift report --dataset <name> --target <url>` for score trends.

Observe commands read `.eva/state.db` in the current directory; another file: `--db <path>`. Standalone runs store nothing, so these show nothing for them.

## Human labels

`eva review queue --failed-only` lists failed invocations. `eva annotate add --invocation <uuid> --label correct` records a verdict; confirm the uuid with `invocations show` first.

## Gotchas

- Judge evaluators (`relevance`, `tone`, `safety`, ...) need a judge model (`EVA_JUDGE_MODEL`) and, in standalone mode, `--prompt` or `--prompt-file`. Without them they are listed under `skipped_judge` and leave the exit code alone: a skipped judge is not a pass.
- `eva init` writes `evals/`, `plugins.py`, `.env` and `eva.yaml` into the current directory; run it only in a fresh one.
- `eva serve --no-auth` opens every route to anyone who can reach the port: pair it with `--host 127.0.0.1`, for local work.
- `--api-key-env` takes the name of an environment variable holding the key, so the key stays out of the command line.
