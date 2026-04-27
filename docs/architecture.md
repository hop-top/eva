# Architecture — Eva

Eva enforces behavioural contracts on AI agents and other CLIs/services. This
document covers the major runtime shapes Eva ships in: the long-running
**gateway** and the **standalone CLI**.

---

## Two invocation paths

| Path | Entry point | Use when |
|------|-------------|----------|
| Gateway | `POST ${EVA_URL}/v1/contract/invoke` | A live agent fronts the contract; production traffic, retries, hints |
| Standalone CLI | `eva run --contract <file> --input <file>` | CI smoke, local dev, pre-recorded artifacts (e.g. flow recordings); no agent, no server |

Both paths dispatch through the **same built-in evaluator registry**
(`core/evaluators/builtin.py::BUILTIN_EVALUATOR_FACTORIES`). Adding a new
built-in evaluator there exposes it to both paths automatically.

```
                 +-------------------------------+
                 | core/evaluators/builtin.py    |
                 |   BUILTIN_EVALUATOR_FACTORIES |
                 +---------------+---------------+
                                 |
            +--------------------+--------------------+
            |                                         |
   +--------v---------+                    +----------v-----------+
   | server/gateway/  |                    | cli/run_contract.py  |
   |   routes.py      |                    |   evaluate_contract  |
   |   (live HTTP)    |                    |   (one-shot CLI)     |
   +------------------+                    +----------------------+
            |                                         |
   POST /v1/contract/invoke              eva run --contract --input
```

See [evaluators-reference.md](evaluators-reference.md) for the full
evaluator catalogue.

---

## Standalone CLI: `eva run --contract --input`

`eva run` operates in **two modes**:

1. **Dataset mode** (existing): `eva run --dataset suite.yaml --target <url>`
   loads a dataset of test cases, calls a live agent for each, evaluates the
   responses. Exit `0` on full pass, `1` on any failure.
2. **Standalone contract mode** (new — T-0258): `eva run --contract c.yaml
   --input data.json` evaluates a single response artifact against a contract.
   No agent call, no gateway. Intended for CI smoke and local dev.

The two modes are mutually exclusive — `--contract`/`--input` cannot be
combined with `--dataset`/`--target`.

### Standalone flow

```
1. Load contract YAML (raw — preserves per-evaluator config)
2. Load input from path or stdin (--input -)
3. For each evaluator in contract.evaluators:
     factory = BUILTIN_EVALUATOR_FACTORIES[name]
     evaluator = factory(spec)            # spec = full evaluator dict
     score = evaluator._run(input_text)
     passed = mode-aware (binary | threshold | warn)
4. Aggregate ContractRunReport
5. Emit text (humans) or JSON (CI) and exit 0 / 1 / 2
```

### Why raw YAML

`load_contract()` returns a `Contract` Pydantic model whose `EvaluatorRef`
stores only `name`, `mode`, `min_score`. Per-evaluator config keys
(`substring`, `pattern`, `schema`, `expected`, ...) are silently dropped.
The standalone runner reads the raw YAML and passes each evaluator dict
to its factory — so config fields survive.

### Exit codes

| Code | Meaning |
|------|---------|
| `0`  | All evaluators passed |
| `1`  | One or more evaluators failed (full JSON/text report on stderr) |
| `2`  | Bad input: missing/malformed contract YAML, missing input file, malformed flags |

### Output sinks

* `--format json` (default in non-TTY / CI): full `ContractRunReport` as JSON.
  Goes to **stdout on pass**, **stderr on fail** — so CI scripts can pipe
  stdout safely on success.
* `--format text` (default in TTY): human table with per-evaluator pass/fail
  rows; final `PASSED`/`FAILED` summary line.
* `--quiet`: suppress passing-evaluator rows in text mode.

### Why no agent call?

The standalone runner takes the agent's response **as a file**. That makes it
ideal for:

* CI gates over flow recordings (e.g. `tlc flow exec` artifacts)
* re-checking past invocations against an updated contract
* deterministic smoke tests where the producer is a CLI, not an HTTP service

For live-agent flows, use dataset mode or the gateway.

---

## Gateway

The gateway (`eva serve`) is a FastAPI service exposing:

* `POST /v1/proxy` — forward request to an upstream agent, then evaluate the
  response against an inline list of evaluators. Supports retry-with-hint.
* `POST /v1/contract/invoke` — same, but the evaluator list comes from a
  named contract loaded from `--contracts-dir`.

Both endpoints persist invocations + artifacts via the storage adapter
(SQLite by default) so observability commands (`eva runs`, `eva invocations`,
`eva failures`) can replay them later.

See [gateway-api.md](gateway-api.md) for the full HTTP surface.
