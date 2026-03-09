# AGENTS.md — Eva

Inherits global rules from `~/.agents/AGENTS.md`. Project-specific overrides below.

---

## Project

Eva — enforcement layer for AI agent behavior. CLI eval tool + production gateway.
Repo: `ideacrafterslabs/eva` | Workspace: `ideacrafterslabs` | Space: `labs`

Three deliverables:
- `core/` — engine (evaluators, adapters, plugin system, models)
- `cli/` — Typer CLI + TUI
- `server/` — FastAPI gateway, contract registry, ARQ queue
- `plugins/` — official adapter packages (separate pyproject.toml each)

---

## Current State

Phase 1 planned. Phases 2–4 planned. No code yet.
All tasks tracked in TLC: `tlc task list --tag phase1` etc.

Plans: `docs/plans/` — one file per phase.
Research: `docs/research/` — landscape + protocol analysis.
Roadmap: `docs/roadmap.md`
Ecosystem (not Eva's to build): `docs/ecosystem.md`

---

## Stack

| Layer | Choice |
|---|---|
| Language | Python 3.11+ |
| CLI | Typer + rich (TUI) |
| Plugin system | pluggy |
| ORM | SQLModel (SQLite default) |
| LLM routing | LiteLLM |
| HTTP framework | FastAPI |
| Task queue | ARQ (Redis) |
| Tracing | OpenTelemetry |
| Protocol | AGNTCY (OASF + ACP) |
| Package mgr | uv |
| Test runner | pytest + pytest-asyncio |

---

## Architecture Rules

- `core/` has zero knowledge of `cli/` or `server/` — no imports across boundary
- `cli/` imports from `core/` only
- `server/` imports from `core/` only
- `plugins/` are independent packages; implement adapter interfaces from `core/`
- All adapters: interface (ABC) in `core/adapters/`, default impl in same file,
  alternatives in `plugins/`
- Contract model is the central primitive — never bypass it
- Never silent failure: always return structured error with `eva_status` + violations

## Evaluator Rules

- Always returns `Score(value: float)` — 0.0–1.0, no exceptions
- Mode (`binary`/`threshold`/`warn`) lives on the evaluator config, not the evaluator
- Tier 1 (deterministic): zero LLM calls — must stay fast and free
- Tier 2 (LLM-judge): always mock `litellm.acompletion` in tests — no real calls
- Tier 3 (custom): user's code — Eva loads it, doesn't own it

---

## TDD Methodology

Doc-first → E2E tests (assert stdout + exit code) → implementation.
Every new feature: write failing test first, run to confirm red, implement, confirm green.
E2E tests use `subprocess` to call the actual CLI binary.

---

## Branch Convention

`{category}/{tlc-id}-{short-description}`
e.g. `feat/T-0001-project-scaffold`, `docs/T-0014-cli-reference`

Never work on `main` directly. Always use worktree: `git hop add <branch>`.

---

## Commit Scope Convention

| Scope | When |
|---|---|
| `feat(core)` | New evaluator, model, adapter, plugin hook |
| `feat(cli)` | New CLI command or flag |
| `feat(server)` | New gateway route, middleware, registry |
| `feat(plugins)` | New official plugin package |
| `test(unit)` | Unit test additions |
| `test(e2e)` | E2E CLI test additions |
| `test(integration)` | Server integration tests |
| `docs` | Any documentation change |

---

## Required Downstream Docs (gate before push)

New public API / CLI command / config option → matching doc task in TLC must exist
and be IN_PROGRESS or DONE before merging.

Phase 1 doc tasks: T-0014–T-0021
Phase 2 doc tasks: T-0059–T-0063
Phase 3 doc tasks: T-0064–T-0069
Phase 4 doc tasks: T-0070–T-0073

---

## Key Design Decisions (do not relitigate)

- AGNTCY/OASF is the native protocol; YAML is the developer DX layer on top
- ARQ over Celery (async-first, Redis already required)
- pluggy over raw importlib (hook lifecycle needed)
- Dashboard is a separate future package — not in this repo
- Domain evaluators (finance/healthcare/legal) are ecosystem, not Eva core
- State backend default: Redis; storage backend default: SQLite
- OTEL spans emitted throughout — never optional, always present (NoopAdapter if
  no backend configured)
