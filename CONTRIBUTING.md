# Contributing to Eva

## CE Contributors

Fork + PR against `hop-top/eva`.

CE code directories:

- `core/` — contract schema, evaluators, runner
- `server/` — FastAPI gateway, ARQ workers, OTEL
- `cli/` — CLI commands
- `plugins/` — plugin registry, bundled plugins

No EE submodule needed for CE development. `ee/` will be empty — this is expected.

## EE Contributors

Requires read access to `hop-top/eva-ee` (private repo).
Request access: hi@hop.top

After cloning CE:

```
git submodule update --init
```

EE code maps to `hop-top/eva-ee` via the `ee/` submodule.
Run EE tests: `just check-ee` (defined in EE repo justfile).

## Setup

```
uv pip install -e ".[dev,server]"
```

For EE contributors, also install EE in editable mode:

```
uv pip install -e "ee/[dev]"
```

## Tests

```
just test        # unit + server tests
just test-e2e    # e2e CLI tests
```

## Commit style

Conventional Commits: `feat|fix|refactor|test|chore|docs`

Examples:

```
feat(core): add timeout evaluator
fix(server): correct rate-limit header parsing
docs(contrib): update setup instructions
```

Scope is optional but encouraged.

## Pull request guidelines

- One logical change per PR.
- Include tests for new behavior.
- Update docs if user-visible behavior changes.
- CHANGELOG entry not required (maintained by maintainers).
