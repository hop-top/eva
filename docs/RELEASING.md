# Releasing Eva

## Pre-Release Checklist

- All tests pass: `just check`
- `CHANGELOG.md` updated — Unreleased items moved to versioned section
- Branch is clean: `git status` shows nothing uncommitted

## Steps

1. Bump version in `pyproject.toml` → `version = "X.Y.ZaN"`
2. Update `CHANGELOG.md` — move Unreleased items under new version heading + date
3. Commit: `git commit -m "chore(release): bump version to X.Y.ZaN"`
4. Tag: `just tag X.Y.ZaN`
5. Dry-run: `just release-dry-run`
6. Push tag: `git push origin vX.Y.ZaN`
7. CI publishes to PyPI automatically (`publish.yml` triggered on `v*` tag)
8. Create GitHub release from tag — paste CHANGELOG section as release notes
9. Attach `dist/` artifacts to release

## CI Setup

The `publish.yml` workflow uses PyPI OIDC trusted publisher — no stored token required.

Configure trusted publisher in PyPI project settings:
- Publisher: GitHub Actions
- Repository: `hop-top/eva`
- Workflow filename: `publish.yml`
- Environment name: `pypi`

## Rollback

- Yank from PyPI: `uv run twine yank eva==X.Y.ZaN`
- Delete tag locally: `git tag -d vX.Y.ZaN`
- Delete tag remotely: `git push origin :refs/tags/vX.Y.ZaN`

## Environment Variables

- `UV_PUBLISH_TOKEN` — PyPI API token (for manual `just publish` only; CI uses OIDC)
