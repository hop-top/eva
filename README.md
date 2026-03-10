# Eva

![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)
![Status](https://img.shields.io/badge/status-alpha-orange.svg)

> Behavioral contract enforcement for AI agents.

## What is Eva?

Eva enforces behavioral contracts on AI agent responses — declarative YAML specs that define
what agents must (and must not) do. Violations are caught before they reach users. Works as a
CLI tool for offline evaluation and as a production gateway proxy that enforces contracts on
live traffic.

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
