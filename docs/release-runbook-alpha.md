# Release Runbook — Eva 0.1.0a1 (Public Alpha)

## Prerequisites

- Branch `main` clean; all CI green.
- `CHANGELOG.md` has `[0.1.0a1]` section with today's date.
- `pyproject.toml` version field set to `0.1.0a1`.
- `UV_PUBLISH_TOKEN` not required (OIDC trusted publisher configured).

---

## Step 1 — Confirm publish.yml green

Verify `publish.yml` workflow passed on tag `v0.1.0a1`:

```
gh run list --workflow=publish.yml --limit=5
gh run view <run-id>
```

All steps green before proceeding.

---

## Step 2 — Create GitHub release from tag

```
gh release create v0.1.0a1 dist/* \
  --title "Eva 0.1.0a1 — Public Alpha" \
  --prerelease
```

- `dist/*`: wheel + sdist produced by CI; download from workflow artifacts if not local.
- `--prerelease`: marks release as pre-release on GitHub.

---

## Step 3 — Paste CHANGELOG body

Edit release body to contain the `[0.1.0a1]` section from `CHANGELOG.md`:

```
gh release edit v0.1.0a1 --notes "$(sed -n '/## \[0\.1\.0a1\]/,/## \[/p' CHANGELOG.md | head -n -1)"
```

Or paste manually in GitHub UI: Releases → v0.1.0a1 → Edit → Notes field.

Body must include:
- Phase 1–3 feature list from CHANGELOG.
- Link to PyPI: `https://pypi.org/project/eva/0.1.0a1/`.
- Link to docs: `https://eva.hop.top/docs`.

---

## Step 4 — Attach dist/ artifacts

Artifacts auto-attached by `gh release create dist/*` in Step 2.

Confirm both files present:
- `eva-0.1.0a1-py3-none-any.whl`
- `eva-0.1.0a1.tar.gz`

```
gh release view v0.1.0a1 --json assets
```

---

## Step 5 — Publish (CI handles automatically)

CI `publish.yml` publishes to PyPI on tag push via OIDC trusted publisher.

Verify package live:

```
pip index versions eva          # shows 0.1.0a1
pip install eva==0.1.0a1        # smoke install
python -c "import eva; print(eva.__version__)"
```

If CI publish failed, publish manually:

```
uv publish --token $UV_PUBLISH_TOKEN
```

---

## Step 6 — Announce

### GitHub Discussions

Post in Discussions → Announcements:

```
Title: Eva 0.1.0a1 — Public Alpha Available

Eva 0.1.0a1 is live on PyPI.

pip install eva[server]

What's included: behavioral contract enforcement, evaluators (exact-match,
regex, semantic, LLM-judge), FastAPI gateway, CLI, plugin system.

Docs: https://eva.hop.top/docs
Release notes: https://github.com/hop-top/eva/releases/tag/v0.1.0a1
Feedback welcome — open an issue or reply here.
```

### README status badge

Confirm PyPI badge in `README.md` resolves to `0.1.0a1`:

```markdown
[![PyPI](https://img.shields.io/pypi/v/eva)](https://pypi.org/project/eva/)
```

Badge auto-updates; no manual change needed.

---

## Post-release checks

| Check | Command |
|---|---|
| PyPI page live | `pip index versions eva` |
| GitHub release visible | `gh release view v0.1.0a1` |
| Artifacts attached | `gh release view v0.1.0a1 --json assets` |
| Badge resolves | Open README.md badge URL in browser |
| Discussion post up | Check GitHub Discussions → Announcements |
