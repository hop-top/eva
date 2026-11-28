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
| `--target` | Optional. Override the target agent URL (replaces a dataset `target:` mapping too). |
| `--provider` | Optional. Chat target provider: `openai` \| `anthropic`. |
| `--base-url` | Optional. Chat target base URL (e.g. `http://localhost:12000/v1`). |
| `--model` | Optional. Chat target model id. |
| `--api-key-env` | Optional. Env var **name** holding the chat target API key. |
| `--max-tokens`, `--temperature`, `--top-p`, `--timeout-s` | Optional. Chat target sampling / timeout. |
| `--concurrency` | Optional. Number of concurrent test executions. Default: `1`. |
| `--no-tui` | Optional. Plain-text output for CI. |

```bash
eva run --dataset evals/my_suite.yaml --target http://localhost:8000/chat

# Chat target: call an OpenAI-compatible model directly
eva run --dataset evals/coding.yaml --no-tui \
  --provider openai --base-url http://localhost:12000/v1 --model my-local-model
```

Chat target flags merge over the dataset's `target:` mapping (flags win);
they cannot be combined with `--target` (exit `2`). See
[dataset-reference.md](dataset-reference.md). Each run prints its
`Run: <id>` for `eva runs show --run-id <id>` / `eva compare`.

### Standalone contract mode

Evaluates a single response artifact against a contract YAML. No agent call,
no gateway. Intended for CI smoke and local dev, e.g. validating a recorded
CLI output. See [architecture.md](architecture.md#standalone-cli-eva-run---contract---input).

| Flag | Description |
|---|---|
| `--contract` | **Required**. Path to the contract YAML. |
| `--input` | **Required**. Path to the input file, or `-` to read from stdin. |
| `--format` | Optional. `text` (default in TTY) or `json` (default in CI). |
| `--quiet` | Optional. Suppress passing-evaluator output (text mode). |
| `--prompt` | Optional. Request prompt text, given to judge evaluators. Not combinable with `--prompt-file`. |
| `--prompt-file` | Optional. Read the request prompt from a file, or `-` for stdin (not when `--input -`). |

```bash
# Recorded output → contract gate (CI)
eva run --contract contracts/my.yaml --input artifacts/response.json --format json

# Pipe from stdin
echo '{"status": "ok"}' | eva run --contract contracts/my.yaml --input -

# Judge evaluators: pass the prompt the response answered
eva run --contract contracts/my.yaml --input artifacts/response.txt \
  --prompt "Summarize the refund policy in two sentences."
```

### Exit Codes:
- `0`: All evaluators passed.
- `1`: One or more evaluators failed (report on stderr).
- `2`: Bad input: missing/malformed contract or input, or invalid flag combo
  (e.g. mixing `--contract` with `--dataset`, `--prompt` together with
  `--prompt-file`, `--prompt`/`--prompt-file` without `--contract`/`--input`, or
  `--prompt-file -` together with `--input -`).

Judge evaluators run when a judge is configured and a prompt is given; see
[llm-evaluators.md](llm-evaluators.md#judge-evaluators-in-contract-mode). Otherwise
they are listed under `skipped_judge` with a reason; exit code unaffected.

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

## `eva data fetch`

Fetch the nltk data the `ifeval_check` evaluator needs (`punkt_tab`, `stopwords`,
`averaged_perceptron_tagger_eng`). Run once per machine; evaluation itself never downloads.
Needs the `ifeval` extra (`pip install "hop-top-eva[ifeval]"`). Resources already present in the
target directory are not fetched again.

| Flag | Description |
|---|---|
| `--dir` | Optional. Target directory. Default: the first `NLTK_DATA` entry if set, else `$XDG_DATA_HOME/eva/nltk_data` (`~/.local/share/eva/nltk_data`). |
| `--dry-run` | Optional. List what would be fetched; no network, no writes. |
| `--format` | Optional. `text` (default in TTY) or `json` (default otherwise). |

`ifeval_check` looks for the data in every `NLTK_DATA` entry, nltk's own search path and the
default directory above. A custom `--dir` must be added to `NLTK_DATA` to be found.

```bash
eva data fetch --dry-run --format json
eva data fetch
```

JSON output: `{"dir": "...", "dry_run": false, "ok": true, "resources": [{"id": "punkt_tab", "status": "fetched"}]}`;
`status` is `present`, `would_fetch`, `fetched` or `failed`.

### Exit Codes:
- `0`: All resources fetched or already present (also for `--dry-run`).
- `1`: A download failed.
- `2`: Invalid flag value (`--format`).
- `3`: The `ifeval` extra (nltk) is not installed.

---

## Global Configuration

Eva can be configured using environment variables in your `.env` file or exported to your shell.

| Variable | Description | Default |
|---|---|---|
| `EVA_STORAGE` | Connection string for results storage. | `sqlite:///.eva/state.db` |
| `EVA_JUDGE_MODEL` | LLM model for Tier 2 evaluators (overrides `judge.model` in `eva.yaml`). Unset: judge evaluators are skipped with a reason. | `None` |
| `EVA_JUDGE_BASE_URL` | OpenAI-compatible endpoint for the judge, e.g. a self-hosted server (overrides `judge.base_url`). See [llm-evaluators.md](llm-evaluators.md#self-hosted-endpoint). | `None` |
| `OPENAI_API_KEY` | API key for hosted OpenAI Tier 2 models. Not sent to a custom `base_url`; use `judge.api_key_env`. | `None` |
