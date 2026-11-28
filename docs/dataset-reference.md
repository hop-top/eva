# Dataset Reference

A dataset is YAML (or JSONL) fed to `eva run --dataset`. Eva calls the
target once per test case, scores the response with the dataset's
evaluators, and stores the run in `.eva/state.db`.

## Shape

```yaml
name: my-suite              # run/dataset name (JSONL: the file stem)
target: <url | mapping>     # where to send each case (see below)
evaluators:                 # run against every case
  - name: code_tests        # built-in name; extra keys = evaluator config
    mode: binary            # binary | threshold | warn
tests:
  - id: case-1              # required, unique
    input: "prompt text"    # required; the user message / {"input": ...}
    expected_output: "6"    # optional; read by exact_match / final_answer
    tests: |                # optional; read by code_tests (string or list)
      assert add(1, 2) == 3
    stdio:                  # optional; code_tests stdin/stdout mode (not with tests)
      - {stdin: "1 2\n", expected_stdout: "3\n"}
    retrieval_context: ...  # optional; RAG judges
    planned_steps: [...]    # optional; plan judges
    metadata: {}            # optional; free-form
```

`ifeval_check` reads `metadata.instruction_id_list` and `metadata.kwargs` (IFEval and
IFBench row fields); see [evaluators-reference.md](evaluators-reference.md#ifeval_check).

An evaluator that needs a case field (`code_tests` -> `tests` or `stdio`;
`exact_match`/`final_answer` -> `expected_output`) is **skipped** for cases
without it, so one dataset can mix code and reasoning cases. A case that
no evaluator applied to is listed under `skipped` (never fails the run).

JSONL: one case per line, same fields; supply the target with `--target`
or the chat flags.

## Append-only datasets

A dataset can declare that its cases are never edited or removed. Results
for a case then stay comparable for as long as the dataset lives, and
growing it is an append.

```yaml
name: pool
target: ...
append_only: true       # opt in; default false (nothing below applies)
```

Datasets without `append_only: true` load and run as described above.

**Directory datasets.** A directory is a dataset: every `*.jsonl` file in
it (sorted by file name, lines in order) holds cases, and an optional
`dataset.yaml` holds the other keys (`name`, `target`, `evaluators`,
`append_only`; no `tests`). File names carry no meaning to eva; the
directory name is the dataset name unless the manifest sets one.

```text
pool/
  dataset.yaml          # name, target, evaluators, append_only: true
  reasoning.jsonl
  coding.jsonl
  dataset.lock.json     # ledger, written by `eva dataset lock`
```

**Case hash.** `core.dataset.case_hash(case)` is the sha256 (hex) of the
canonical JSON of the case's content fields: `id`, `input`,
`expected_output`, `retrieval_context`, `planned_steps`, `tests` (a list is
joined with newlines, so it equals the string form), `supersedes`, `tools`,
`tool_choice` and `stdio`.
Unset fields are omitted. Keys are sorted, separators compact, text UTF-8
without ASCII escaping. The hash depends on that case alone, so adding
other cases never changes it. `metadata` is **not** hashed: provenance can
be corrected without invalidating stored results.

**Ledger.** `eva dataset lock` records `case id -> case hash` in a JSON
file kept with the dataset (one line per id), so the check works on any
machine: `suite.lock.json` next to `suite.yaml`, or `dataset.lock.json`
inside a directory. Commit it with the dataset.

**Superseding a wrong case.** Never edit it. Append a new case with
`supersedes: <old id>`. The old case stays in the dataset and the ledger
but is not run or scored (`eva run`, TUI totals). `supersedes` must name
another existing case and may not form a cycle.

**Provenance.** Every case of an append-only dataset needs
`metadata.source`, `metadata.licence`, `metadata.added` (ISO date) and
`metadata.origin` (`import`, `failure` or `handwritten`). Other datasets
are never checked for it.

```jsonl
{"id": "gsm-0001", "input": "...", "expected_output": "6", "metadata": {"source": "gsm8k", "licence": "MIT", "added": "2026-03-01", "origin": "import"}}
{"id": "gsm-0001b", "supersedes": "gsm-0001", "input": "...", "expected_output": "7", "metadata": {"source": "gsm8k", "licence": "MIT", "added": "2026-03-05", "origin": "failure"}}
```

`eva dataset check` fails (exit `3`) on: a recorded case whose hash
changed (`edited`), a recorded case that disappeared (`removed`), an id
used twice (`collision`), a case not yet in the ledger (`unrecorded`),
missing or invalid provenance (`provenance`) and a bad `supersedes`
(`supersedes`). `eva run` performs the same check first and exits `3`
without running anything. See
[cli-reference.md](cli-reference.md#eva-dataset).

Public benchmark sets can be imported with seeded, append-only sampling:
see [dataset-importers.md](dataset-importers.md).

## Key facts

The `key_facts` evaluator reads `metadata.key_facts` from each case:

```yaml
tests:
  - id: eiffel-summary
    input: "Summarize: ..."
    metadata:
      key_facts:
        required:                     # each item is one fact
          - "Paris"                   # a string = a single accepted variant
          - ["1889", "eighteen eighty-nine"]   # a list = variants, any counts
        forbidden: ["Berlin"]         # optional; any hit scores 0
```

`required` items are non-empty strings or non-empty lists of strings; `forbidden` is a list of
strings. Malformed facts score `0.0` with an `invalid facts` reason. A case without
`metadata.key_facts` falls back to the evaluator's `required`/`forbidden` config, or is skipped
if that is empty. See [evaluators-reference.md](evaluators-reference.md#key_facts).

## Targets

### URL target (unchanged)

```yaml
target: http://localhost:8000/chat
```

Eva `POST`s `{"input": "<case input>"}` and scores the body text.
`--target <url>` overrides it.

### Chat target

```yaml
target:
  provider: openai                      # openai | anthropic
  base_url: http://localhost:12000/v1
  model: my-local-model                 # any id the endpoint accepts
  api_key_env: MY_ENDPOINT_KEY          # optional; env var NAME
  max_tokens: 2048                      # optional
  temperature: 0.0                      # optional
  top_p: 1.0                            # optional
  timeout_s: 120                        # optional, default 120
  system: "You are a careful engineer." # optional, eva addition
```

Field names match hop-top/ben endpoint configs, so a config is portable
between the two tools (`system` is eva-only). Unknown keys are rejected.
Unset sampling fields are not sent.

| Provider | Request | Auth |
|---|---|---|
| `openai` | `POST {base_url}/chat/completions` (OpenAI-compatible: OpenAI, mlx_lm.server, Ollama `/v1`, vLLM). Default base URL `https://api.openai.com/v1`. | `Authorization: Bearer $<api_key_env>` only when `api_key_env` is set. `OPENAI_API_KEY` is never read implicitly. |
| `anthropic` | Messages API. `base_url` may be the host, a `/v1` root or the full `/v1/messages` URL (default `https://api.anthropic.com`). `max_tokens` defaults to 4096 (required by the API). | `x-api-key: $<api_key_env>` (default `ANTHROPIC_API_KEY`), `anthropic-version: 2023-06-01`. |

Responses:
- The evaluated output is the **answer only**. Reasoning from
  `reasoning_content` / `reasoning` (openai), `thinking` blocks
  (anthropic), or inline `<think>…</think>` (including a lone `</think>`)
  is removed and stored separately as a `reasoning` artifact on the
  invocation (`eva invocations show --id <id>`).
- Model id (as echoed by the server), provider, latency (model call only)
  and token usage are recorded per case.
- Transport errors, non-2xx statuses and malformed bodies mark the case
  `upstream_error` (evaluator `target`, score 0, reason kept) and the run
  continues. A missing `api_key_env` variable is reported the same way.

The run's `target` in the store is the label `provider:model@base_url`,
so runs of the same model/endpoint group together (`eva runs list
--target`, drift) and different models are different targets.

Add providers with `core.chat_targets.register_chat_provider`.

### Tool definitions per case

A case may offer tools to a chat target with two optional fields, in
OpenAI format:

```yaml
tests:
  - id: weather-paris
    input: What is the weather in Paris?
    tool_choice: required          # optional: auto | none | required | {type: function, function: {name: ...}}
    tools:
      - type: function
        function:
          name: get_weather
          description: Current weather for a city
          parameters:
            type: object
            properties: {city: {type: string}}
            required: [city]
```

`tool_choice` requires `tools`. Cases without `tools` send a request
identical to before.

- `openai`: `tools` and `tool_choice` are sent verbatim in the
  `/chat/completions` body (OpenAI, Ollama `/v1`, mlx_lm.server, vLLM).
- `anthropic`: each tool becomes `{name, description, input_schema}`;
  `tool_choice` maps `auto` -> `auto`, `required` -> `any`, `none` ->
  `none`, a named function -> `{type: tool, name}`.
- URL targets ignore `tools`.

One request is sent. Eva does not run the tools and sends no follow-up
turn: every tool call in the reply is recorded in the case's tool-call
log (see [Tool-call log](evaluators-reference.md#tool-call-log)). A reply
without tool calls records an empty log, not an error.

### Expected tool calls

For the `tool_call_match` evaluator a case lists its expected calls under
`metadata.expected_calls`; no other case field is involved. Format, modes
and options: [`tool_call_match`](evaluators-reference.md#tool_call_match).

```yaml
tests:
  - id: weather-paris
    input: What is the weather in Paris?
    tools: [...]
    metadata:
      expected_calls:
        - get_weather: {city: [Paris], unit: [celsius, ""]}
```

Sample dataset:
[`examples/tool-call-match.yaml`](examples/tool-call-match.yaml).

### Target identity

Stored per-case results are keyed by a **target id** that must not depend
on the machine. `Run.target` for a chat target carries the base URL
(`provider:model@base_url`), which differs between machines; the target id
does not:

| Target | Target id |
|---|---|
| chat target | `provider:model` (base URL and sampling settings are not part of it) |
| URL target | the URL |
| explicit | `id:` in the chat `target:` mapping, a top-level `target_id:`, or `eva run --target-id` (flag wins) |

Two configurations that must not share results (different system prompt or
temperature, say) need different explicit ids. The sampling settings used
are not stored in a record.

```yaml
target:
  provider: openai
  model: my-model
  id: my-model-greedy
```

The evaluator name `target` is reserved (it marks upstream errors); a
dataset that uses it fails to load (exit `2`).

### CLI overrides

```sh
eva run --dataset suite.yaml \
  --provider openai --base-url http://localhost:12000/v1 --model my-local-model \
  [--api-key-env ENV] [--max-tokens N] [--temperature T] [--top-p P] [--timeout-s S]
```

Flags merge over the dataset's `target:` mapping (flags win), or build the
target for a dataset with a URL/no target. `--target <url>` and chat flags
are mutually exclusive (exit `2`). Keep `--concurrency 1` (default) for
local single-GPU servers.

## Example

[`examples/local-openai-coding-reasoning.yaml`](examples/local-openai-coding-reasoning.yaml)
— one coding case (`code_tests`) and one reasoning case (`final_answer`)
against a local OpenAI-compatible server:

```sh
eva run --dataset docs/examples/local-openai-coding-reasoning.yaml --no-tui
# e.g.
#   ✓ code-add · code_tests (1830ms)
#   ✓ reason-apples · final_answer (940ms)
# Results: 2/2 Passed.  Run: 3fa91c02

eva runs show --run-id 3fa91c02
```

## Case categories

A case names its category and when it was added in `metadata`:

```yaml
tests:
  - id: add-2
    input: "..."
    expected_output: "4"
    metadata:
      category: arithmetic      # string; groups the per-category figures
      added: 2026-03-05         # ISO date; read by --since
```

`eva run`, `eva runs show` and `eva compare` report passed/total per
category next to the overall result. A case passes when every evaluator
that applied to it passed.

- A case without `metadata.category` is reported under the
  `uncategorised` bucket (so a category literally named `uncategorised`
  shares it). It is never dropped.
- A case that no evaluator applied to is not scored: it is neither a pass
  nor a fail, is left out of every passed/total figure, and is reported as
  "not scored".
- `--since YYYY-MM-DD` adds the figure for scored cases whose
  `metadata.added` is on or after that date. Cases without a valid
  `metadata.added` are excluded from it and their number is printed.
- `eva run --format json` carries `"categories": {"<name>": {"passed": n,
  "total": n}}`, `"cases"` (per case: `test_id`, `category`, `added`,
  `scored`, `passed`) and, with `--since`, `"since": {"since", "passed",
  "total", "excluded"}`.
- `runs show` and `compare` derive the same figures from the stored
  invocations (each keeps its case's category and added date in its
  metadata) and evaluator results.

## Per-case results

A result for a case on a target stays valid as long as the case is
unchanged, so results are kept per case, not per run. Query and move them
with `eva results` ([cli-reference.md](cli-reference.md#eva-results-list--export--import)).

A record is keyed by `(dataset, target_id, case, case_hash)`. `case_hash` is
`sha256:` followed by the hex digest from the case hash described under
[Append-only datasets](#append-only-datasets) (the results layer adds the
prefix, so the algorithm shows in stored data). The first record for a key
stands; later runs do not change it. Not recorded: cases whose target call
failed (they carry the `target` pseudo-evaluator result and an
`upstream_error` invocation) and cases no evaluator applied to.
A case passes when every evaluator that applied to it passed; `score` is the
mean of their scores.

```json
{"v": 1, "dataset": "my_suite", "target_id": "openai:my-model",
 "case": "code-add", "case_hash": "sha256:9f2c...", "passed": true,
 "score": 1.0,
 "evaluators": [{"name": "code_tests", "passed": true, "score": 1.0,
                 "reason": null, "mode": "binary"}],
 "run_id": "3fa91c02", "at": "2026-01-02T03:04:05+00:00",
 "provider": "openai", "model": "my-model"}
```

`at` is the UTC start of the run that produced the record. `v` is the
record version (`1`); an import refuses other versions.

Export layout: `<dir>/<dataset>/<target>.jsonl`, one record per line, keys
sorted, lines sorted by case, hash, date. Directory and file names are the
dataset name and target id with characters outside `A-Za-z0-9._-` replaced by
`_`, plus an 8-character hash of the original, so distinct ids never share a
file. The files are meant to be tracked in git: they merge as line appends.

## Comparing models over time

Every `eva run` writes the run, one invocation per case and one `agent`
usage record per chat call to `.eva/state.db`:

- `eva runs list --dataset local-coding-reasoning` — runs, pass counts.
  `--format json` on `runs list` / `runs show` for scripts
  ([cli-reference.md](cli-reference.md#eva-runs-list--eva-runs-show)).
- `eva runs show --run-id <id>` — per case: provider, model, status,
  total duration, **model latency**, **tokens in/out**.
- `eva invocations show --id <inv>` — request, response (answer only),
  reasoning, evaluator reasons (e.g. the failing assertion), usage.
- `eva compare --left <run> --right <run>` — models, invocation counts,
  cost, **average model latency**, **prompt/completion tokens**, and
  per-evaluator pass rate (e.g. `code_tests` 100% -> 50%) and per-category
  passed/total (see [Case categories](#case-categories)).

Cost is blank for local models (no pricing).

## Security

`code_tests` executes model output in a contained subprocess (throwaway
directory, scrubbed environment, time/memory/file limits, network and
filesystem containment where the OS allows). It is hardening, not a security
boundary. See [evaluators-reference.md](evaluators-reference.md#code_tests).
