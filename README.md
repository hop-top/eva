# Eva

![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)

> Enforcement & Validation for Agents: deterministic, binary pass/fail validator.

> **Status:** Active development. Usable today, with some rough edges as features evolve.

## What is Eva?

Eva enforces and validates behavioral contracts on AI agent responses — declarative YAML specs
that define what agents must (and must not) do. Violations are caught before they reach users.
Works as a CLI tool for offline evaluation and as a production gateway proxy that enforces
contracts on live traffic.

## Install

```sh
pip install hop-top-eva          # core + CLI
pip install hop-top-eva[server]  # + gateway server
```

Or with uv:

```sh
uv add hop-top-eva
uv add hop-top-eva[server]
```

## Development

Working on eva itself (not just consuming it):

```sh
git clone https://github.com/hop-top/eva && cd eva
make setup    # uv sync --extra dev --extra server
make test     # unit + e2e (excludes optional plugin tests)
```

`make` targets: `setup`, `test`, `test-all`, `lint`, `format`,
`typecheck`, `links`, `check` (lint + typecheck + test + links),
`build`, `clean`. Run `make` (no target) or read the Makefile for the
full list.

**Why `--extra dev --extra server` matters:** `pytest` lives in the
`dev` extra; `httpx`/FastAPI test plumbing lives in `server`. Plain
`uv sync` resolves the venv but does NOT install test deps —
`uv run pytest` will then fail with a confusing `ModuleNotFoundError`.
The Makefile's `setup` target handles this; always prefer `make` over
raw `uv` invocations for local dev.

`tests/plugins/` is excluded by `make test` — those tests require optional
plugin packages (`eva-a2a`, `eva-mcp`, `eva-otlp`, etc.) that aren't
declared in any extra. Install them individually if you need them.

## Quickstart

**1. Initialize a contract:**

```sh
eva init my-contract.yaml
```

**2. Run evaluation against a response:**

```sh
eva run my-contract.yaml
```

**3. Start the gateway server:**

```sh
eva serve
```

The gateway listens on `http://localhost:8000` and proxies requests through contract
enforcement before forwarding to the upstream agent.

## Grading models (chat targets)

`eva run --dataset` can call an LLM chat API directly (no agent URL) and
score the answer, so local and cloud models are comparable over time in
`.eva/state.db` (`eva runs list`, `eva runs show`, `eva compare`):

```sh
eva run --dataset docs/examples/local-openai-coding-reasoning.yaml --no-tui \
  --provider openai --base-url http://localhost:12000/v1 --model my-local-model
```

Providers: `openai` (any OpenAI-compatible server: OpenAI, mlx_lm.server,
Ollama `/v1`, vLLM) and `anthropic`; pluggable. Model id, provider,
latency and token usage are recorded per case; reasoning
(`reasoning_content`, `reasoning`, `<think>…</think>`) is stored separately
and never scored. Built-in evaluators for model grading: `code_tests`
(runs generated code against per-case unit tests), `final_answer`
(`Final answer: X` line) and `exact_match`.

> [!CAUTION]
> `code_tests` and `code_test_passes` **execute model output** on the
> machine running eva. Use them only on trusted runs, inside a sandbox
> (container/VM/throwaway user). Isolation is best-effort: no network or
> filesystem blocking.

Full reference: [docs/dataset-reference.md](docs/dataset-reference.md).

## Key Concepts

- **Contracts** — YAML specs defining expected agent behavior; version-controlled,
  shareable, composable.
- **Evaluators** — pluggable checks. Deterministic: `contains`, `regex`,
  `json_schema_valid`, `no_pii`, `exact_match`, `final_answer`, ... ; LLM-judge:
  `relevance`, `hallucination`, ... (need `EVA_JUDGE_MODEL`). Code:
  `code_block_runs` only **parses** fenced blocks (python/json/yaml/sh);
  `code_test_passes` and `code_tests` **execute** the generated code
  (see [evaluators-reference.md](docs/evaluators-reference.md)).
- **Gateway** — FastAPI proxy enforcing contracts on live traffic; hot-reloads contract
  changes.
- **Plugins** — extend storage, OTEL export, importers (A2A, MCP) via pluggy entry points.

## Links

[Docs](docs/) | [Roadmap](docs/roadmap.md) | [Contributing](CONTRIBUTING.md) |
[Changelog](CHANGELOG.md) | [Issues](https://github.com/hop-top/eva/issues)
