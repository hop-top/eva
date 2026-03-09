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

Execute an evaluation suite against a target agent.

### Arguments & Flags:
| Flag | Description |
|---|---|
| `--dataset` | **Required**. Path to the evaluation dataset (YAML or JSONL). |
| `--target` | Optional. Override the target agent URL. |
| `--concurrency` | Optional. Number of concurrent test executions. Default: `1`. |

### Usage:
```bash
eva run --dataset evals/my_suite.yaml --target http://localhost:8000/chat
```

### Exit Codes:
- `0`: All tests passed according to the contract.
- `1`: One or more tests failed.

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
