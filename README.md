# Eva

> [!WARNING]
> **🚧 Do Not Use — History Will Be Rewritten 🚧**
>
> This repo is undergoing major restructuring as we selectively
> open-source internal tools built at
> [Idea Crafters LLC](https://ideacrafters.com). Git history **will be
> force-pushed and rewritten** multiple times. Do not fork, clone, or
> depend on this repo in any capacity until we tag a stable release.


![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)
![Status](https://img.shields.io/badge/status-alpha-orange.svg)

> Enforcement & Validation for Agents: deterministic, binary pass/fail validator.

## What is Eva?

Eva enforces and validates behavioral contracts on AI agent responses — declarative YAML specs
that define what agents must (and must not) do. Violations are caught before they reach users.
Works as a CLI tool for offline evaluation and as a production gateway proxy that enforces
contracts on live traffic.

## Install

```sh
pip install eva          # core + CLI
pip install eva[server]  # + gateway server
```

Or with uv:

```sh
uv add eva
uv add eva[server]
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

## Key Concepts

- **Contracts** — YAML specs defining expected agent behavior; version-controlled,
  shareable, composable.
- **Evaluators** — pluggable checks: `contains`, `regex`, `json_schema`, `no_pii`,
  `llm_judge`.
- **Gateway** — FastAPI proxy enforcing contracts on live traffic; hot-reloads contract
  changes.
- **Plugins** — extend storage, OTEL export, importers (A2A, MCP) via pluggy entry points.

## Links

[Docs](docs/) | [Roadmap](docs/roadmap.md) | [Contributing](CONTRIBUTING.md) |
[Changelog](CHANGELOG.md) | [Issues](https://github.com/hop-top/eva/issues)
