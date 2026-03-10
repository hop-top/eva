# Changelog

All notable changes to Eva are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
Versioning: [PEP 440](https://peps.python.org/pep-0440/)

## [Unreleased]

## [0.1.0a1] - 2026-03-09

### Added — Phase 1: Core Foundation
- Contract YAML spec + loader
- Evaluators: `contains`, `regex_match`, `json_schema_valid`, `no_pii`
- CLI: `eva init`, `eva run`, `eva contract validate`, `eva contract diff`
- SQLite storage adapter, OTEL adapter stubs
- Plugin system via pluggy

### Added — Phase 2: Core Power
- LLM-as-judge evaluator (litellm backend)
- Concurrency modes: async, sync, threaded
- Redis state adapter
- OTEL exporter adapter
- `eva contract diff` rich TUI output

### Added — Phase 3: Server + Plugins
- FastAPI gateway: `eva serve`, `POST /v1/proxy`, `POST /v1/contract/invoke`
- Contract registry + hot-reload (watchfiles)
- Request schema validation middleware
- Retry + self-healing engine with hint injection
- ARQ async evaluation queue
- Official plugins: `eva-postgres`, `eva-otlp`, `eva-a2a`, `eva-mcp`

### Added — Phase 4: Hardening
- API key authentication middleware (`X-Eva-Key`)
- Drift detection: `eva drift report` CLI
- EE: rate limiting (sliding window, Redis)
- EE: webhook emission on violations
- EE: `eva-agntcy` plugin (ACP manifest, `/.well-known/agent.json`)

[0.1.0a1]: https://github.com/hop-top/eva/releases/tag/v0.1.0a1
