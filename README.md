# Eva — Enforcement Layer for AI Agent Behavior

Eva is a developer-centric evaluation and enforcement toolkit for AI agents. It provides a standardized way to define, test, and enforce "contracts" that specify the expected behavior and quality standards for your agents.

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

## Why Eva?

As AI agents move from experimental prototypes to production systems, "vibes-based" evaluation is no longer enough. Engineering teams need rigorous, repeatable, and automated ways to ensure their agents are safe, reliable, and compliant.

Eva provides the **enforcement layer** that bridges the gap between raw LLM capabilities and production-grade software requirements.

### Key Differentiators
- **Contract-First**: Define behavioral expectations in human-readable YAML before you write a single line of agent code.
- **Enforcement, not just Observation**: Eva is designed to act as a production gateway (sidecar proxy) that can block non-compliant requests or responses in real-time.
- **Protocol Native**: Built from the ground up to support AGNTCY, OASF, and ACP standards, ensuring interoperability across the agentic ecosystem.

### When NOT to use Eva
- You are doing pure exploratory research and don't need behavioral guarantees yet.
- You prefer a "black box" approach to agent evaluation without explicit contract definitions.

## Installation

Eva is currently in early development. You can install it via `pip`:

```bash
pip install eva-core
```

### Requirements
- Python 3.11+
- Redis (for state management/rate limiting - optional in Phase 1)

## Usage

Define a contract in YAML and run evaluations against your agent endpoint.

```yaml
# evals/refund_policy.yaml
name: refund_policy
provider: billing-agent
evaluators:
  - name: json_schema_valid
    mode: binary
  - name: contains
    substring: "refund"
    mode: binary
```

Run the evaluation suite:

```bash
eva run --dataset evals/suite.yaml --target http://localhost:8000/chat
```

## Comparisons

| Feature | Eva | LangSmith | Promptfoo |
|---------|-----|-----------|-----------|
| **Core Focus** | Enforcement | Observability | Offline Eval |
| **Contracts** | YAML (OASF) | Proprietary | YAML/JSON |
| **Gateway Mode**| Yes (Sidecar) | No | No |
| **Protocols** | AGNTCY Native | None | None |

## Documentation

- [Concepts Guide](docs/concepts-guide.md) — How Eva works.
- [Quickstart Guide](docs/quickstart-guide.md) — Zero to first eval in 5 minutes.
- [Contract YAML Reference](docs/contract-yaml-reference.md) — Schema and properties.
- [Built-in Evaluators Reference](docs/evaluators-reference.md) — Available test types.
- [Plugin Authoring Guide](docs/plugin-authoring-guide.md) — Extend Eva with custom logic.
- [CLI Reference](docs/cli-reference.md) — Commands and flags.

## Roadmap

Eva is following a 4-phase roadmap:
- [x] **Phase 1**: Core Foundation (Local CLI + Deterministic Evals)
- [ ] **Phase 2**: Core Power (LLM-as-judge + TUI + Concurrency)
- [ ] **Phase 3**: Server + Plugins (FastAPI Gateway + Official Adapters)
- [ ] **Phase 4**: Hardening + AGNTCY Alignment

## Contributing

Contributions are welcome! Please see [docs/roadmap.md](docs/roadmap.md) to see where we're headed.

## License

Eva is licensed under the MIT License. See the [LICENSE](LICENSE) file for more information.
