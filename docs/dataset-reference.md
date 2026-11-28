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
    retrieval_context: ...  # optional; RAG judges
    planned_steps: [...]    # optional; plan judges
    metadata: {}            # optional; free-form
```

An evaluator that needs a case field (`code_tests` -> `tests`;
`exact_match`/`final_answer` -> `expected_output`) is **skipped** for cases
without it, so one dataset can mix code and reasoning cases. A case that
no evaluator applied to is listed under `skipped` (never fails the run).

JSONL: one case per line, same fields; supply the target with `--target`
or the chat flags.

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

## Comparing models over time

Every `eva run` writes the run, one invocation per case and one `agent`
usage record per chat call to `.eva/state.db`:

- `eva runs list --dataset local-coding-reasoning` — runs, pass counts.
- `eva runs show --run-id <id>` — per case: provider, model, status,
  total duration, **model latency**, **tokens in/out**.
- `eva invocations show --id <inv>` — request, response (answer only),
  reasoning, evaluator reasons (e.g. the failing assertion), usage.
- `eva compare --left <run> --right <run>` — models, invocation counts,
  cost, **average model latency**, **prompt/completion tokens**, and
  per-evaluator pass rate (e.g. `code_tests` 100% -> 50%).

Cost is blank for local models (no pricing).

## Security

`code_tests` executes model output. See
[evaluators-reference.md](evaluators-reference.md#code_tests).
