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
| `--target-id` | Optional. Identity of the target in stored per-case results (see `eva results`). Default: `provider:model` for chat targets, the URL otherwise. |
| `--concurrency` | Optional. Number of concurrent test executions. Default: `1`. |
| `--no-tui` | Optional. Plain-text output for CI. |
| `--since` | Optional. `YYYY-MM-DD`. Also report accuracy on cases whose `metadata.added` is on or after the date. Invalid date: exit `2`. |
| `--missing` | Optional. Run only the cases the target has no stored result for (see [Running only missing cases](#running-only-missing-cases)). |
| `--category NAME` | With `--missing`. Only cases whose `metadata.category` equals `NAME`. |
| `--limit N` | With `--missing`. At most `N` cases: the first `N` missing ones, in dataset order. `N` below `1`: exit `2`. |
| `--dry-run` | Optional. Print the case ids that would run and exit `0`: no target call, nothing stored. |
| `--format` | Optional. `text` (default) or `json`. |

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

### Running only missing cases

`eva run --dataset D --missing` runs only the cases the target has no
stored result for (per-case results, see
[`eva results`](#eva-results-list--export--import)). The target is identified
as in [dataset-reference.md](dataset-reference.md#target-identity) (`--target-id`
included). A case counts as having a result when a record exists for the case
id at the case's **current** content hash, passed or failed, so:

- a fresh target runs every case; a second run runs none; after cases are
  appended to an append-only dataset only the new ones run;
- a case edited since its result (a non-append-only dataset) is missing again;
- superseded cases of an append-only dataset never run;
- a case whose target call failed (upstream error) and a case no evaluator
  applied to were never recorded, so they run again every time.

`--category NAME` and `--limit N` narrow the selection and need `--missing`.
Cases are selected before any target call. A run stores its results as usual,
so the next `--missing` run skips them.

```bash
eva run --dataset bench/ --provider openai --base-url http://localhost:12000/v1 \
  --model my-model --missing --category math --limit 20
eva run --dataset bench/ --provider openai --model my-model --missing --dry-run
```

With nothing missing, `eva run --missing` exits `0` and prints
`Nothing to run: <target id> has a result for every case of <dataset>.`
`--dry-run` prints `Would run N of S cases of <dataset> for <target id>:` and
the case ids, one per line.

With `--format json`, `--dry-run` and a run with nothing to do write one
object instead of a run:

```json
{"dataset": "bench", "target_id": "openai:my-model", "dry_run": true,
 "missing_only": true, "scored": 120, "missing": 3, "selected": ["c118", "c119", "c120"]}
```

`scored` is the number of cases the dataset runs (superseded ones excluded);
`missing` (only with `--missing`) the number of those without a result, after
`--category`; `selected` the ids that would run, after `--limit`;
`missing_only` whether `--missing` was given. `--dry-run` without `--missing`
selects every scored case. A run that does execute prints the run as usual.

`--missing`, `--category`, `--limit` and `--dry-run` apply to dataset mode;
with `--contract`/`--input` they exit `2`. `--category` and `--limit` without
`--missing` exit `2`.

### Per-category figures

Cases carry `metadata.category`; `eva run` prints passed/total per category
after the results, `--format json` carries them under `categories`, and
`eva runs show --run-id <id>` and `eva compare --left <a> --right <b>` show
the same figures for stored runs. Both accept `--since YYYY-MM-DD` like
`eva run` (invalid date: exit `2`). Cases without a category are reported
as `uncategorised`; cases no evaluator applied to are not scored. Details:
[dataset-reference.md](dataset-reference.md#case-categories).

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
- `2` also, in dataset mode: an evaluator's configuration is invalid; the message
  names the evaluator and the problem and no target call is made (see
  [evaluators-reference.md](evaluators-reference.md#invalid-evaluator-configuration)).
- `2` also: `--category`/`--limit` without `--missing`, `--limit` below `1`, or
  `--missing`/`--dry-run`/`--category`/`--limit` with `--contract`.
- `3`: Dataset mode only: the dataset is append-only and its integrity check
  failed (see [`eva dataset`](#eva-dataset)); nothing ran.

Judge evaluators run when a judge is configured and a prompt is given; see
[llm-evaluators.md](llm-evaluators.md#judge-evaluators-in-contract-mode). Otherwise
they are listed under `skipped_judge` with a reason; exit code unaffected.

### Output sinks (standalone mode):
- On **pass**: report goes to **stdout** (pipe-safe).
- On **fail**: report goes to **stderr**; stdout stays empty.

---

## `eva runs list` / `eva runs show`

Query runs stored in `.eva/state.db` (or the file given by `--db`).

| Flag | Command | Description |
|---|---|---|
| `--dataset`, `--target`, `--status pass\|fail`, `--limit` | `list` | Filters; `--limit` defaults to `50`. |
| `--run-id` | `show` | **Required**. Run to inspect. |
| `--db` | both | Optional. Path to the SQLite DB file. |
| `--format` | both | Optional. `text` (default, tables) or `json`. |

```bash
eva runs list --dataset my_suite --format json
eva runs show --run-id 3fa91c02 --format json
```

With `--format json`, stdout carries exactly one JSON object and nothing
else; errors go to stderr. Both shapes are objects, so fields can be added
without breaking readers.

`eva runs list --format json`:

```json
{
  "runs": [
    {
      "run_id": "3fa91c02",
      "dataset": "my_suite",
      "target": "openai:my-model@http://localhost:12000/v1",
      "status": "fail",
      "passed": false,
      "started_at": "2026-01-02T03:04:05",
      "duration_ms": 120,
      "summary": {"passed": 1, "total": 2}
    }
  ]
}
```

No matching runs gives `{"runs": []}` and exit `0`. `summary` counts
evaluator results (one per case and evaluator), as the text table does.

`eva runs show --format json`:

```json
{
  "run": { "...": "same fields as one entry of runs list" },
  "invocations": [
    {
      "invocation_id": "...", "test_id": "c1", "provider": "openai",
      "model": "my-model", "status": "pass", "duration_ms": 50,
      "model_latency_ms": 40, "prompt_tokens": 7, "completion_tokens": 3,
      "contract_name": null
    }
  ],
  "results": [
    {"test_id": "c1", "evaluator": "contains", "passed": true,
     "score": 1.0, "reason": null}
  ]
}
```

Values that were not recorded are `null`. `invocations` is capped at 500
entries.

### Exit Codes:
- `0`: Output written (including an empty `runs` list).
- `1`: `runs show`: run not found (message on stderr in `json` mode).
- `2`: Bad input: `--format` other than `text` or `json`, or a missing or
  unknown flag.

---

## `eva invocations show`

Full detail for one invocation: header fields, request and response
artifacts, then tables of evaluator results, tool calls and usage. Ids come
from `eva runs show` or `eva failures list`. Data model:
[observability-data-model.md](observability-data-model.md).

| Flag | Description |
|---|---|
| `--id` | **Required**. Invocation id. |
| `--db` | Optional. Path to the SQLite DB file (default `.eva/state.db`). |

```bash
eva invocations show --id 0b6f2c1e-4a8d-4f57-9a3e-6d1c2e7f8a90
```

### Exit Codes:
- `0`: Invocation shown.
- `1`: Invocation not found (`Invocation not found: <id>`).
- `2`: Missing or unknown flag.

---

## `eva compare`

Two runs side by side: model(s), invocation count, total cost, average model
latency, prompt and completion tokens (one summary table), per-evaluator
pass rates, and per-category pass rates when cases carry a category
(see [Per-category figures](#per-category-figures)). Cost, latency and token
rows come from stored usage records; the diff column is right minus left.
For two targets across many runs use [`eva results compare`](#eva-results-compare).

| Flag | Description |
|---|---|
| `--left` | **Required**. Baseline run id. |
| `--right` | **Required**. New run id. |
| `--since` | Optional. ISO date `YYYY-MM-DD`; also compares accuracy on cases whose `metadata.added` is on or after it. |
| `--db` | Optional. Path to the SQLite DB file. |

```bash
eva compare --left 3fa91c02 --right 77be0d15
```

### Exit Codes:
- `0`: Comparison shown.
- `1`: A run id is not found (`Error: Run(s) not found: ['<id>']`).
- `2`: Bad `--since` date, or a missing or unknown flag.

---

## `eva failures list`

Failed evaluator results, one row per failure: invocation id, dataset,
model, evaluator, score, reason. Filters combine with AND.

| Flag | Description |
|---|---|
| `--evaluator` | Optional. Evaluator name. |
| `--model` | Optional. Model name. |
| `--contract` | Optional. Contract name. |
| `--dataset` | Optional. Dataset name. |
| `--limit` | Optional. Max rows; default `50`. |
| `--db` | Optional. Path to the SQLite DB file. |

```bash
eva failures list --evaluator contains --model gpt-4o --limit 20
```

### Exit Codes:
- `0`: Table shown, or `No failures found.` when nothing matches.
- `2`: Missing or unknown flag.

---

## `eva usage report`

Token totals and cost by model, over every stored invocation or only those
matching the filters. Prints the invocation count, prompt, completion and
total tokens, estimated cost in USD, and a per-model table.

| Flag | Description |
|---|---|
| `--dataset` | Optional. Dataset name. |
| `--target` | Optional. Target URL or id, as stored on the invocation. |
| `--db` | Optional. Path to the SQLite DB file. |

```bash
eva usage report --dataset my_suite
```

Cost sums the `estimated_cost_usd` stored with each usage record. `eva run`
stores token counts without a cost estimate, so for run data the cost
columns read `$0.000000`; the token columns are real.

### Exit Codes:
- `0`: Report shown (zeros when nothing matches).
- `2`: Missing or unknown flag.

---

## `eva annotate add` / `eva annotate list` / `eva review queue`

Human review of stored invocations. Workflow, columns and examples:
[annotation-guide.md](annotation-guide.md).

| Command | Flags | Description |
|---|---|---|
| `eva annotate add` | `--invocation` (**required**), `--label`, `--score` (`0.0`-`1.0`), `--notes`, `--reviewer` (default `human`), `--db` | Store an annotation; prints its id. |
| `eva annotate list` | `--invocation` (**required**), `--db` | List the annotations on an invocation. |
| `eva review queue` | `--failed-only`, `--db` | Invocations with no annotation or with a failing evaluator result; `--failed-only` keeps only the latter. |

```bash
eva annotate add --invocation 0b6f2c1e --label wrong --score 0.0 --notes "missed refund"
eva review queue --failed-only
```

### Exit Codes:
- `0`: Done, including an empty list or queue. `annotate add` does not check
  that the invocation id exists.
- `2`: Missing or unknown flag.

---

## `eva results list` / `export` / `import` / `compare`

Per-case results per target, kept across runs. Every `eva run` in dataset
mode stores one record per case in `.eva/state.db` (or the `--db` file),
keyed by dataset, target id, case id and case hash. The **first result for a
key stands**: later runs never change it. Not recorded, so retried on a
later run: cases whose target call failed (upstream error) and cases no
evaluator applied to. Record and file format:
[dataset-reference.md](dataset-reference.md#per-case-results).

| Command | Flags |
|---|---|
| `eva results list` | `--dataset` (required, name as stored), `--target`, `--status pass\|fail`, `--limit` (1000), `--dataset-file`, `--db`, `--format text\|json` |
| `eva results export` | `--dataset` (required), `--dir` (required), `--target`, `--dataset-file`, `--dry-run`, `--db`, `--format text\|json` |
| `eva results import PATH...` | files or directories of `*.jsonl`, `--dry-run`, `--db`, `--format text\|json` |
| `eva results compare` | `--dataset` (required), `--left-target` (required), `--right-target` (required), `--since DATE`, `--dataset-file`, `--db`, `--format text\|json` |

`--dataset-file PATH` (a dataset file or directory) restricts list/export
to that dataset's current scored cases: superseded cases and results for a
case whose content changed drop out. It refuses a dataset with duplicate
case ids (exit `2`). Without it, every stored record for the dataset name is
used, so a non-append-only dataset whose case text changed keeps one record
per case hash.

```bash
eva results list --dataset my_suite --target openai:my-model --format json
eva results export --dataset my_suite --dir results/ --dry-run
eva results import results/
```

`--format json` writes one JSON object to stdout; messages and conflict
lines go to stderr.

- `list`: `{"results": [record, ...]}`, ordered by target, case, hash, date.
  No match gives `{"results": []}`, exit `0`.
- `export`: `{"dry_run": bool, "files": [{"path", "records"}], "conflicts": [...]}`.
  Writes `<dir>/<dataset>/<target>.jsonl`. An existing file is merged, not
  replaced: records it holds that the store lacks are kept. Re-exporting an
  unchanged store is byte-identical. `--dry-run` writes nothing.
- `import`: `{"dry_run", "inserted", "unchanged", "replaced", "conflicts": [...],
  "hash_mismatches": [...]}`. Idempotent. `--dry-run` reports only.

- `compare`: see below.

Import conflict rules (the same merge is used when exporting into an
existing file):

- Key absent: inserted.
- Key present, same content (ignoring run id and date): unchanged.
- Key present, different content: the record with the earlier `at` stands
  (tie: smaller `run_id`); the pair is reported as a conflict with
  `kept_run_id` and `other_run_id`. Nothing is overwritten silently.
- Same case under another case hash: both are kept and listed under
  `hash_mismatches`.
- A malformed line or unsupported record version aborts the whole import
  with nothing written.

### `eva results compare`

Two targets on one dataset, from stored per-case results (not from runs), so
a target's results may span many runs. `eva compare --left RUN --right RUN`
compares two runs; this compares two targets.

```bash
eva results compare --dataset my_suite --left-target openai:a \
  --right-target openai:b --dataset-file datasets/my_suite --format json
```

A case is **shared** when both targets hold a result for it at the same case
hash. Only shared cases are counted. A case both targets answered under
different case hashes is not shared (they saw different text) and is counted
in `excluded.hash_mismatch`. With `--dataset-file`, superseded cases and
results at a stale hash are dropped first, as in `list`, so such a case counts
as answered by one side only. Without it every stored record for the dataset
name is used.

Figures are per category (`metadata.category`, `uncategorised` when absent),
which needs `--dataset-file`; without it there is one `overall` bucket and no
categories (the text output says so). `--since YYYY-MM-DD` adds one more
bucket over shared cases whose `metadata.added` is on or after the date; it
needs `--dataset-file`. Shared cases without a usable `added` are left out of
it and counted in `excluded_no_added`.

`--format json` writes one object:

```json
{"dataset": "my_suite", "left_target": "openai:a", "right_target": "openai:b",
 "categorised": true,
 "overall": {"shared": 3, "left_passed": 2, "right_passed": 2,
             "left_rate": 0.6667, "right_rate": 0.6667, "diff": 0.0,
             "only_left": ["a"], "only_right": ["b"]},
 "categories": {"code": {"...": "same fields as overall"}},
 "excluded": {"hash_mismatch": 1, "left_only": 2, "right_only": 0},
 "since": {"date": "2026-01-01", "...": "bucket fields", "excluded_no_added": 0}}
```

- `left_passed` / `right_passed`: shared cases each side passed.
  `*_rate` is that over `shared` (4 decimals); `diff` is `right_rate -
  left_rate`. All three are `null` when `shared` is `0`.
- `only_left`: shared case ids left passed and right failed; `only_right`:
  the reverse. Sorted.
- `categories` is `{}` and `categorised` `false` without `--dataset-file`.
  `since` appears only with `--since`.
- `excluded.left_only` / `right_only`: case ids answered by that side only.

Exit codes for `compare`: `0` done (also when no case is shared); `2` bad
input: unknown target (no stored results for it in the dataset), both targets
equal, bad `--since` or `--since` without `--dataset-file`, bad `--format`,
unreadable dataset file or duplicate case ids.

### Exit Codes:
- `0`: Done (including nothing to do and empty lists).
- `1`: `import` / `export` found conflicts (the earlier result is kept).
- `2`: Bad input: bad `--format` or `--status`, unreadable or malformed
  JSONL, missing path, unreadable dataset file, duplicate case ids with
  `--dataset-file`.

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

## `eva dataset`

Integrity commands for [append-only datasets](dataset-reference.md#append-only-datasets)
(`append_only: true`). `PATH` is a YAML dataset or a directory of JSONL
files. All four accept `--format text|json` (default `text`; JSON goes to
stdout, problems in text mode to stderr).

| Command | What it does |
|---|---|
| `eva dataset check PATH` | Fails if a recorded case was edited or removed, an id is used twice, a case is not in the ledger, provenance is missing/invalid or a `supersedes` is bad. Writes nothing. |
| `eva dataset lock PATH [--dry-run]` | Records new cases in the ledger. Refuses (writes nothing) on any problem other than the cases being unrecorded. |
| `eva dataset add PATH --from CASES.jsonl [--file NAME.jsonl] [--dry-run]` | Directory datasets only. Appends the cases to `NAME.jsonl` (created if new; optional when the directory holds exactly one `.jsonl`) and records them. A case whose id and content hash are already present is skipped; the same id with different content is refused. Nothing is written if any case is refused. `--from -` reads stdin. |
| `eva dataset import SOURCE --into DIR [--n N] [--seed S] [--file NAME.jsonl] [--dry-run]` | Samples cases from a public benchmark set and appends them to an append-only directory dataset; see [dataset-importers.md](dataset-importers.md). |

```bash
eva dataset check pool/ --format json
# {"ok": true, "cases": 120, "scored": 118, "superseded": 2, "problems": []}
eva dataset add pool/ --from new-cases.jsonl --file reasoning.jsonl --dry-run
```

JSON shapes: `check` -> `ok, cases, scored, superseded, problems`;
`lock` -> `ok, dry_run, recorded, problems`; `add` -> `ok, dry_run, added,
skipped, problems`; `import` -> `ok, dry_run, source, seed, requested,
sampled, revision, added, skipped, problems`. Each problem is `{code, id, message}` with `code` one of
`edited`, `removed`, `collision`, `unrecorded`, `provenance`, `supersedes`,
`conflict`, `invalid`.

### Exit Codes:
- `0`: Check passed / cases recorded or added.
- `1`: `import` only: upstream unreachable or unusable; nothing was written.
- `2`: Bad input: dataset not found or unreadable, not append-only,
  invalid `--format`, unusable `--file`; for `import` also an unknown or
  refused source.
- `3`: Integrity check failed; nothing was written.

`eva run --dataset` on an append-only dataset runs the same check first
and exits `3` (problems on stderr) without calling the target.

## `eva skill show`

Print the agent skill bundled with this eva version to stdout. Read-only; always
serves the bundled copy, never an installed one.

### Arguments:
| Argument | Description |
|---|---|
| `reference` | Optional. Name of a reference file, without `.md` (`rest-api`, `contract-yaml`, `benchmarks`). Omit to print `SKILL.md`. |

### Usage:
```bash
eva skill show
eva skill show rest-api
```

### Exit Codes:
- `0`: Printed.
- `2`: Unknown reference name; the message lists the valid names.

---

## `eva skill install`

Copy the bundled skill into a directory and write `.skill-install.json`
(`{"tool", "version", "files": {path: sha256}}`). Nothing is installed unless
you run this.

| Flag | Description |
|---|---|
| `--dir` | Optional. Target directory. Default: `~/.claude/skills/eva-cli`. |
| `--dry-run` | Optional. Print what would be written, replaced or removed; write nothing. |
| `--force` | Optional. Overwrite a modified or foreign copy. Files eva did not install are kept. |

- Target missing or empty: files are written.
- Target with a manifest whose files all still match their hashes: files are
  replaced, and manifest-listed files that are no longer bundled are removed.
- Target without a manifest, with a modified or missing file, or with files the
  manifest does not list: refused (exit `1`, offending files named) unless `--force`.

### Usage:
```bash
eva skill install
eva skill install --dir ./skills/eva-cli --dry-run
```

---

## Global Configuration

Eva can be configured using environment variables in your `.env` file or exported to your shell.

| Variable | Description | Default |
|---|---|---|
| `EVA_STORAGE` | Connection string for results storage. | `sqlite:///.eva/state.db` |
| `EVA_JUDGE_MODEL` | LLM model for Tier 2 evaluators (overrides `judge.model` in `eva.yaml`). Unset: judge evaluators are skipped with a reason. | `None` |
| `EVA_JUDGE_BASE_URL` | OpenAI-compatible endpoint for the judge, e.g. a self-hosted server (overrides `judge.base_url`). See [llm-evaluators.md](llm-evaluators.md#self-hosted-endpoint). | `None` |
| `OPENAI_API_KEY` | API key for hosted OpenAI Tier 2 models. Not sent to a custom `base_url`; use `judge.api_key_env`. | `None` |
