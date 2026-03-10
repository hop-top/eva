# Eva GitHub Action

Run [Eva](https://github.com/hop-top/eva) behavioral contract evaluations in your CI/CD pipeline
using the official reusable GitHub Action.

---

## Basic usage

Add a workflow file to your repository:

```yaml
# .github/workflows/eva.yml
name: Eva Contract Evaluation

on: [push, pull_request]

jobs:
  eva:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run Eva contract evaluation
        uses: hop-top/eva@main
        with:
          contracts-dir: ./evals
          dataset: ./evals/test-dataset.jsonl
          fail-on-violation: true
```

This checks out your code, installs Eva, validates your contracts, runs evaluations against
your dataset, and fails the build if any violations are found.

---

## Inputs reference

| Input | Description | Default |
|-------|-------------|---------|
| `contracts-dir` | Path to the directory containing contract YAML files | `./evals` |
| `dataset` | Path to dataset file or glob pattern | `./evals/*.jsonl` |
| `eva-version` | Eva version to install. Use `"latest"` for the newest release | `latest` |
| `python-version` | Python version used to run Eva | `3.11` |
| `fail-on-violation` | Fail the workflow if any contract violations are found | `true` |
| `no-tui` | Disable rich TUI output for cleaner CI logs | `true` |
| `extra-args` | Additional arguments passed verbatim to `eva run` | `""` |

---

## Outputs reference

| Output | Description |
|--------|-------------|
| `violations` | Number of violations found (`0` if none) |
| `result` | `pass` if no violations, `fail` otherwise |

Outputs can be accessed in subsequent steps via `steps.<step-id>.outputs.<output>`:

```yaml
- name: Run Eva
  id: eva
  uses: hop-top/eva@main
  with:
    contracts-dir: ./evals
    dataset: ./evals/dataset.jsonl

- name: Report result
  run: echo "Eva result: ${{ steps.eva.outputs.result }} (violations: ${{ steps.eva.outputs.violations }})"
```

---

## Advanced examples

### Pin to a specific Eva version

```yaml
- name: Run Eva contract evaluation
  uses: hop-top/eva@main
  with:
    contracts-dir: ./evals
    dataset: ./evals/dataset.jsonl
    eva-version: '0.4.2'
```

### Pass extra arguments to `eva run`

Use `extra-args` to forward any flags supported by `eva run` that are not covered by
dedicated inputs:

```yaml
- name: Run Eva contract evaluation
  uses: hop-top/eva@main
  with:
    contracts-dir: ./evals
    dataset: ./evals/dataset.jsonl
    extra-args: '--concurrency 4 --timeout 30'
```

### Non-blocking mode (report without failing)

Set `fail-on-violation: false` to collect results without blocking the build. Useful for
gradual rollouts or informational checks on feature branches:

```yaml
- name: Run Eva contract evaluation
  id: eva
  uses: hop-top/eva@main
  with:
    contracts-dir: ./evals
    dataset: ./evals/dataset.jsonl
    fail-on-violation: false

- name: Annotate PR with Eva result
  if: github.event_name == 'pull_request'
  run: |
    echo "### Eva Evaluation: ${{ steps.eva.outputs.result }}" >> $GITHUB_STEP_SUMMARY
    echo "Violations detected: ${{ steps.eva.outputs.violations }}" >> $GITHUB_STEP_SUMMARY
```

### Use a different Python version

```yaml
- name: Run Eva contract evaluation
  uses: hop-top/eva@main
  with:
    contracts-dir: ./evals
    dataset: ./evals/dataset.jsonl
    python-version: '3.12'
```

### Matrix strategy across multiple datasets

```yaml
jobs:
  eva:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        dataset:
          - ./evals/smoke.jsonl
          - ./evals/regression.jsonl
    steps:
      - uses: actions/checkout@v4

      - name: Run Eva — ${{ matrix.dataset }}
        uses: hop-top/eva@main
        with:
          contracts-dir: ./evals
          dataset: ${{ matrix.dataset }}
          fail-on-violation: true
```

---

## How it works

The action runs the following steps internally:

1. **Set up Python** — installs the requested Python version via `actions/setup-python`.
2. **Install uv** — installs the [uv](https://github.com/astral-sh/uv) package manager.
3. **Install Eva** — installs `eva[server]` at the requested version using `uv pip install`.
4. **Validate contracts** — runs `eva contract validate` on every YAML file in
   `contracts-dir` as a pre-flight check (failures are non-fatal at this stage).
5. **Run Eva evaluation** — executes `eva run` with your dataset and contracts, captures
   the exit code, and writes `violations` and `result` to `$GITHUB_OUTPUT`.
6. **Check result** — fails the build if `fail-on-violation` is `true` and violations
   were detected.
