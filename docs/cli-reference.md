# CLI Reference — Eva

The `eva` command-line interface provides tools for managing Eva projects, validating contracts, and running evaluations.

---

## `eva init`

Scaffold a new Eva project structure in the current directory.

### Output:
- Creates `evals/` directory for your contract and dataset YAML files.
- Creates `eva_plugins.py` template for custom evaluators.
- Creates `.env` file for project-specific configuration.

### Usage:
```bash
eva init
```

---

## `eva run`

Execute evaluations. Two modes — **dataset** (live agent) and **standalone
contract** (offline; no agent, no gateway).

### Dataset mode

Loads a dataset of test cases and calls a live agent for each.

| Flag | Description |
|---|---|
| `--dataset` | **Required**. Path to the evaluation dataset (YAML or JSONL). |
| `--target` | Optional. Override the target agent URL. |
| `--concurrency` | Optional. Number of concurrent test executions. Default: `1`. |
| `--no-tui` | Optional. Plain-text output for CI. |

```bash
eva run --dataset evals/my_suite.yaml --target http://localhost:8000/chat
```

### Standalone contract mode

Evaluates a single response artifact against a contract YAML. No agent call,
no gateway. Intended for CI smoke and local dev, e.g. validating a recorded
output from `tlc flow exec`. See [architecture.md](architecture.md#standalone-cli-eva-run---contract---input).

| Flag | Description |
|---|---|
| `--contract` | **Required**. Path to the contract YAML. |
| `--input` | **Required**. Path to the input file, or `-` to read from stdin. |
| `--format` | Optional. `text` (default in TTY) or `json` (default in CI). |
| `--quiet` | Optional. Suppress passing-evaluator output (text mode). |

```bash
# Recorded output → contract gate (CI)
eva run --contract contracts/my.yaml --input artifacts/response.json --format json

# Pipe from stdin
echo '{"status": "ok"}' | eva run --contract contracts/my.yaml --input -
```

### Exit Codes:
- `0`: All evaluators passed.
- `1`: One or more evaluators failed (report on stderr).
- `2`: Bad input: missing/malformed contract or input, or invalid flag combo
  (e.g. mixing `--contract` with `--dataset`).

### Output sinks (standalone mode):
- On **pass**: report goes to **stdout** (pipe-safe).
- On **fail**: report goes to **stderr**; stdout stays empty.

---

## `eva contract validate`

Check the syntax and schema of a contract YAML file.

### Arguments:
| Argument | Description |
|---|---|
| `path` | **Required**. Path to the contract YAML file to validate. |

### Usage:
```bash
eva contract validate contracts/refund_policy.yaml
```

### Exit Codes:
- `0`: Contract is valid.
- `1`: Contract contains validation errors.

---

## Global Configuration

Eva can be configured using environment variables in your `.env` file or exported to your shell.

| Variable | Description | Default |
|---|---|---|
| `EVA_STORAGE` | Connection string for results storage. | `sqlite:///.eva/state.db` |
| `EVA_JUDGE_MODEL` | LLM model to use for Tier 2 evaluators. | `openai/gpt-4o-mini` |
| `OPENAI_API_KEY` | API key for Tier 2 (LLM) evaluations. | `None` |
