.PHONY: build test test-all lint format typecheck links check setup \
       promote promote-alpha promote-beta promote-rc \
       promote-release

check: lint typecheck test links

build:
	uv build

test: setup
	uv run pytest tests/unit/ tests/e2e/ --ignore=tests/plugins

test-all: setup
	uv run pytest

lint: setup
	uv run ruff check .

format: setup
	uv run ruff format .

typecheck: setup
	uv run mypy core/ cli/ server/

links:
	@if command -v lychee >/dev/null 2>&1; then \
		lychee --no-progress .; \
	else \
		echo "lychee not installed; skipping link check"; \
	fi

setup:
	uv sync --extra dev --extra server
	@command -v lychee >/dev/null 2>&1 || true

promote:
	@scripts/promote-release.sh

promote-alpha promote-beta promote-rc promote-release:
	@scripts/promote-release.sh $(subst promote-,,$@)
