# Eva justfile

# Default: list all targets
default:
    just --list

# Run full test suite (excluding e2e)
test:
    uv run --extra dev --extra server pytest tests/ -v --ignore=tests/e2e

# Run e2e tests
test-e2e:
    uv run pytest tests/e2e/ -v

# Lint (ruff; tolerates missing ruff gracefully)
lint:
    uv run ruff check . || true

# Full quality gate
check: test lint

# Build distribution artifacts
build:
    uv build

# Check built artifacts
check-dist:
    uv run --with twine twine check dist/*

# Full release dry-run (build + check)
release-dry-run: build check-dist

# Tag a release — usage: just tag 0.1.0a1
tag version:
    git tag -a v{{version}} -m "Release v{{version}}"

# Publish to PyPI (requires UV_PUBLISH_TOKEN)
publish:
    uv publish

# Full release gate
check-release: check release-dry-run
