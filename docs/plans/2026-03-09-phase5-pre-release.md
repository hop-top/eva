# Phase 5: Packaging + Pre-Release Prep — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan
> task-by-task.

<!-- Task list
  T-0091 Task 1  CE licensing + pyproject.toml metadata
  T-0092 Task 2  README
  T-0093 Task 3  CHANGELOG
  T-0094 Task 4  RELEASING.md + justfile release targets
  T-0095 Task 5  Quality gate + release dry-run
  T-0096 Task 6  PyPI publish CI workflow
  T-0097 Task 7  GitHub release v0.1.0a1
  T-0098 Task 8  EE repo init (hop-top/eva-ee)
  T-0099 Task 9  Git submodule wire (ee/ in CE)
  T-0100 Task 10 Private PyPI (Cloudflare R2)
  T-0101 Task 11 Partner onboarding doc
  T-0102 Task 12 Beta release v0.1.0b1
-->

**Goal:** Package Eva for public alpha (CE, PyPI) and private beta (CE+EE, private PyPI). Establish
dual-licensing, release tooling, and partner distribution infrastructure.

**Gates:** Alpha (`0.1.0a1`, public PyPI, CE only) → Beta (`0.1.0b1`, private PyPI, CE+EE)

**Assumes:** Phases 1–4 complete.

---

## Gate 1 — Public Alpha (`eva==0.1.0a1`)

### Task 1: CE licensing + pyproject.toml metadata

**Files:**
- `LICENSE` (create)
- `pyproject.toml` (edit)

**Steps:**
1. Write `LICENSE` — Apache 2.0 full text; copyright `hop-top`; year `2026`.
2. In `pyproject.toml` `[project]` table add:
   - `license = {text = "Apache-2.0"}`
   - `description = "Eva — behavioral contract enforcement for AI agents"`
   - `authors = [{name = "hop-top", email = "hi@hop.top"}]`
   - `keywords = ["ai", "agents", "contracts", "evaluation", "gateway"]`
   - `classifiers`:
     - `"Development Status :: 3 - Alpha"`
     - `"Intended Audience :: Developers"`
     - `"Topic :: Software Development :: Libraries"`
     - `"Programming Language :: Python :: 3.11"`
     - `"Programming Language :: Python :: 3.12"`
     - `"License :: OSI Approved :: Apache Software License"`
3. Add `[project.urls]` table:
   - `Homepage = "https://eva.hop.top"`
   - `Repository = "https://github.com/hop-top/eva"`
   - `Documentation = "https://eva.hop.top/docs"`
   - `"Bug Tracker" = "https://github.com/hop-top/eva/issues"`

**Expected outcome:** `uv build` produces wheel with correct metadata; `twine check dist/*` passes.

**Commit message:** `chore(release): CE Apache 2.0 license + pyproject metadata`

---

### Task 2: README

**Files:**
- `README.md` (rewrite; keep <150 lines)

**Steps:**
1. Badges row: PyPI version shield, Apache-2.0 shield, CI status shield.
2. One-liner tagline beneath project name.
3. **What is Eva** — 3–4 sentence intro: behavioral contract enforcement, evaluators, gateway.
4. **Install** section:
   ```pseudocode
   pip install eva[server]  # or: uv add eva[server]
   ```
5. **Quickstart** — three steps:
   ```pseudocode
   eva init my-contract.yaml
   eva run my-contract.yaml
   eva serve
   ```
6. **Concepts** — bulleted: contracts, evaluators, gateway; each with one-line description.
7. **Links** — docs, roadmap, contributing, changelog.
8. Keep telegraphic style; no marketing fluff.

**Expected outcome:** README renders cleanly on GitHub; badge links resolve; <150 lines.

**Commit message:** `docs(release): README — badges, quickstart, concepts`

---

### Task 3: CHANGELOG

**Files:**
- `CHANGELOG.md` (create)

**Steps:**
1. Use Keep a Changelog format (`## [Unreleased]` + versioned sections).
2. Add `[0.1.0a1] - 2026-03-09` section with sub-sections:
   - **Added — Phase 1 (Core Foundation):**
     contract schema, evaluators (exact-match, regex, semantic, LLM-judge),
     CLI (`eva init`, `eva run`, `eva validate`, `eva contract diff`),
     SQLModel persistence, pluggy plugin system.
   - **Added — Phase 2 (Core Power):**
     storage adapters (Redis, SQLite, in-memory), LLM-judge evaluator via litellm,
     concurrency modes (sequential, parallel, async), async runner.
   - **Added — Phase 3 (Server + Plugins):**
     FastAPI server, gateway proxy, ARQ background workers, OTEL instrumentation,
     plugin registry, `eva serve` command.
3. Add comparison link at bottom: `[0.1.0a1]: https://github.com/hop-top/eva/releases/tag/v0.1.0a1`

**Expected outcome:** `CHANGELOG.md` follows spec; single `[0.1.0a1]` entry covers all shipped phases.

**Commit message:** `chore(release): CHANGELOG — 0.1.0a1 covers phases 1–3`

---

### Task 4: RELEASING.md + justfile release targets

**Files:**
- `docs/RELEASING.md` (create)
- `justfile` (create — confirmed not present)

**Steps:**

#### docs/RELEASING.md
1. **Pre-release checklist:** all tests pass (`just check`); CHANGELOG updated; branch clean.
2. **Bump version:** edit `pyproject.toml` `version` field to target version (e.g. `0.1.0a1`).
3. **Update CHANGELOG:** move items from `[Unreleased]` to new versioned section; add date.
4. **Commit:** `chore(release): bump version to 0.1.0a1`.
5. **Tag:** `just tag version=0.1.0a1` → creates `v0.1.0a1`.
6. **Dry-run:** `just release-dry-run` — builds wheel+sdist; runs twine check.
7. **Publish:** `just publish` — pushes to PyPI (requires `UV_PUBLISH_TOKEN`).
8. **GitHub release:** create release from tag; paste CHANGELOG section; attach dist files.
9. **EE gate (beta only):** repeat steps 2–8 in `eva-ee` repo targeting private PyPI.

#### justfile
```pseudocode
# default: list targets
default:
    just --list

# lint + typecheck + tests
check:
    run: ruff check .
    run: pyright .
    run: pytest tests/

# build wheel + sdist; validate distributions
release-dry-run:
    run: uv build
    run: twine check dist/*

# publish to PyPI (requires UV_PUBLISH_TOKEN env var)
publish:
    run: uv publish

# tag current commit with v{version}
tag version:
    run: git tag v{version}
    run: git push origin v{version}

# full pre-publish gate
check-release: check release-dry-run
```

**Expected outcome:** `just --list` shows all targets; `just release-dry-run` executes without error.

**Commit message:** `chore(release): RELEASING.md + justfile release targets`

---

### Task 5: Quality gate + release dry-run

**Files:**
- `justfile` (edit — add `check-release` if missing)

**Steps:**
1. Run `just check` — confirm lint, typecheck, tests all green.
2. Run `just release-dry-run` — confirm wheel + sdist build; twine check passes.
3. Note required env vars in `docs/RELEASING.md` under **Environment**:
   - `UV_PUBLISH_TOKEN` — PyPI API token (for `just publish`; not needed for OIDC CI).
4. Fix any issues found before proceeding to Task 6.
5. Record gate result as commit message note.

**Expected outcome:** Zero failures in `just check-release`; dist files present in `dist/`.

**Commit message:** `chore(release): quality gate green — 0.1.0a1 dry-run passes`

---

### Task 6: PyPI publish CI workflow

**Files:**
- `.github/workflows/publish.yml` (create)

**Steps:**
1. Set trigger: `on: push: tags: ["v*"]`.
2. Single job `publish` on `ubuntu-latest`:
   ```pseudocode
   step: checkout (fetch-depth 0)
   step: setup Python 3.11
   step: install uv
   step: uv build
   step: publish to PyPI using OIDC trusted publisher
         (environment: pypi; no token in secrets)
   ```
3. Configure PyPI trusted publisher in PyPI project settings:
   - Publisher: GitHub Actions
   - Repo: `hop-top/eva`
   - Workflow: `publish.yml`
   - Environment: `pypi`
4. Document trusted-publisher setup steps in `docs/RELEASING.md` under **CI Setup**.

**Expected outcome:** Pushing `v0.1.0a1` tag triggers workflow; wheel published to PyPI without
stored secrets.

**Commit message:** `ci(release): PyPI publish workflow — OIDC trusted publisher`

---

### Task 7: GitHub release v0.1.0a1

**Files:** (no code files — procedural steps)

**Steps:**
1. Confirm `publish.yml` workflow green on tag `v0.1.0a1`.
2. Run: `gh release create v0.1.0a1 dist/* --title "Eva 0.1.0a1 — Public Alpha"`.
3. Body: paste `[0.1.0a1]` section from `CHANGELOG.md`.
4. Mark as pre-release (`--prerelease` flag).
5. Announce in project channels; link PyPI page.

**Expected outcome:** GitHub release `v0.1.0a1` visible; dist files attached; PyPI page live.

**Commit message:** `chore(release): tag + release v0.1.0a1`

---

## Gate 2 — Private Beta (`eva==0.1.0b1` + `eva-ee==0.1.0b1`)

### Task 8: EE repo init (`hop-top/eva-ee`)

**Files (in `eva-ee` repo):**
- `LICENSE` (BSL 1.1)
- `README.md`
- `pyproject.toml`

**Steps:**
1. **Manual step:** create `hop-top/eva-ee` private repo on GitHub (UI or `gh repo create`).
2. Write `LICENSE`:
   - License: Business Source License 1.1
   - Licensor: hop-top
   - Licensed Work: Eva EE
   - Change Date: 2030-03-09
   - Change License: Apache-2.0
   - Additional Use Grant:
     > You may use the Licensed Work for your own internal business operations.
     > Competing AI contract enforcement services offered as a product or service
     > require a separate commercial license.
3. Write `pyproject.toml` for `eva-ee`:
   - `name = "eva-ee"`
   - `version = "0.1.0b1"`
   - `requires-python = ">=3.11"`
   - `dependencies = ["eva>=0.1.0b1"]`
   - metadata fields mirroring CE (authors, keywords, classifiers with BSL classifier)
4. Write `README.md` — brief: what EE adds, install from private PyPI, contact for access.

**Expected outcome:** `hop-top/eva-ee` repo exists; BSL 1.1 LICENSE committed; package buildable.

**Commit message:** `chore(release): EE repo init — BSL 1.1 license, pyproject stub`

---

### Task 9: Git submodule wire (`ee/` in CE)

**Files (in CE repo):**
- `.gitmodules` (auto-created by git submodule add)
- `CONTRIBUTING.md` (edit or create)

**Steps:**
1. In CE repo root:
   ```pseudocode
   git submodule add git@github.com:hop-top/eva-ee.git ee/
   git commit -m "chore(release): add ee/ submodule → hop-top/eva-ee"
   ```
2. Edit/create `CONTRIBUTING.md` — add **EE Contributors** section:
   - EE contributors need read access to `hop-top/eva-ee` (request via hi@hop.top).
   - Activate submodule: `git submodule update --init`.
   - CE works without EE present; `ee/` dir is empty for non-EE contributors.
   - Run EE tests: `just check-ee` (defined in EE repo justfile).
3. Add note to `docs/RELEASING.md` — beta release requires synced submodule pointer.

**Expected outcome:** `ee/` submodule present in CE; CE builds/tests pass without EE init'd.

**Commit message:** `chore(release): wire ee/ submodule, document in CONTRIBUTING.md`

---

### Task 10: Private PyPI (Cloudflare R2)

**Files (in `eva-ee` repo):**
- `.github/workflows/publish-ee.yml` (create)

**Steps:**
1. **Create R2 bucket** (Cloudflare dashboard or `wrangler`):
   - Bucket name: `eva-private-pypi`
   - Region: auto
2. **Configure index URL** for partners:
   ```pseudocode
   index_url = "https://eva-private-pypi.{account-id}.r2.cloudflarestorage.com/simple/"
   ```
3. Create `.github/workflows/publish-ee.yml` in `eva-ee`:
   ```pseudocode
   trigger: push tags matching v*
   job: publish-ee on ubuntu-latest
     step: checkout
     step: setup Python 3.11 + uv
     step: uv build
     step: uv publish --index-url {R2_INDEX_URL}
           env: R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY (from repo secrets)
   ```
4. Add R2 API token to `hop-top/eva-ee` repo secrets:
   - `R2_ACCESS_KEY_ID`
   - `R2_SECRET_ACCESS_KEY`
5. Document index URL in `ee/docs/partner-setup.md` (Task 11).

**Expected outcome:** Pushing `v0.1.0b1` to `eva-ee` publishes wheel to R2 private index.

**Commit message:** `ci(release): EE publish workflow — Cloudflare R2 private PyPI`

---

### Task 11: Partner onboarding doc

**Files:**
- `ee/docs/partner-setup.md` (create in `eva-ee` repo, exposed via submodule)

**Steps:**
1. **Obtain credentials** — contact hi@hop.top; receive R2 read token pair.
2. **Configure pip/uv:**
   ```pseudocode
   # uv
   uv add eva-ee \
     --index-url https://eva-private-pypi.{account}.r2.cloudflarestorage.com/simple/ \
     --extra-index-url https://pypi.org/simple/
   # pip
   pip install eva-ee \
     --index-url https://... \
     --extra-index-url https://pypi.org/simple/
   ```
3. **Verify install:**
   ```pseudocode
   python -c "import eva_ee; print(eva_ee.__version__)"
   ```
4. **Submodule setup (contributors only):**
   ```pseudocode
   git submodule update --init
   cd ee/
   uv sync
   ```
5. **Environment:** set `UV_INDEX_URL` / `PIP_INDEX_URL` in `.env` or CI secrets.
6. **Support:** issues → hi@hop.top; SLA: best-effort during beta.

**Expected outcome:** Partner can install `eva-ee` from private index and verify import.

**Commit message:** `docs(release): partner onboarding — R2 private PyPI setup guide`

---

### Task 12: Beta release `v0.1.0b1`

**Files:**
- `pyproject.toml` in CE repo (version bump)
- `pyproject.toml` in `eva-ee` repo (version bump)
- `CHANGELOG.md` in CE repo (add `[0.1.0b1]` section)

**Steps:**
1. Bump CE `pyproject.toml` version → `0.1.0b1`; update CHANGELOG with `[0.1.0b1]` section.
2. Commit + tag `v0.1.0b1` in CE repo; push tag → triggers `publish.yml` → CE wheel to PyPI.
3. Bump `eva-ee` `pyproject.toml` version → `0.1.0b1`; confirm `eva>=0.1.0b1` dep.
4. Commit + tag `v0.1.0b1` in `eva-ee`; push tag → triggers `publish-ee.yml` → EE wheel to R2.
5. Update CE submodule pointer to `eva-ee` `v0.1.0b1` commit.
6. Create GitHub releases on both repos (mark pre-release).
7. Notify design partners: index URL, credentials reminder, feedback channel.

**Expected outcome:** `eva==0.1.0b1` on public PyPI; `eva-ee==0.1.0b1` on private R2 index;
design partners can install both.

**Commit message:** `chore(release): bump versions + tag v0.1.0b1, beta release`
