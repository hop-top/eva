# Eva Cheatsheet — Human

Quick reference for daily eval + gateway use. Scannable in 30 seconds.

---

## Install

```bash
pip install eva             # core + CLI
pip install eva[server]     # + gateway server
uv add eva[server]          # preferred
```

---

## Init

```bash
eva init                    # scaffold evals/, plugins.py, .env, eva.yaml
eva version                 # verify
```

Config: `eva.yaml` (project root) · DB: `.eva/state.db`

---

## Contracts

```bash
eva contract validate my-contract.yaml     # parse + validate
eva contract diff v1.yaml v2.yaml          # detect regressions (exit 1 if found)
```

### Contract YAML structure

```yaml
name: refund_policy
provider: http://billing-agent/chat        # upstream agent URL
consumer: support-agent
request_schema:
  type: object
  required: [order_id]
  properties:
    order_id: {type: string}
evaluators:
  - name: json_schema_valid
    mode: binary                           # binary | graded
    min_score: 1.0
  - name: no_pii
    mode: binary
retry_policy:
  max_retries: 3
  hint: "Return valid JSON, no PII"
```

---

## Eval Runs (Offline)

```bash
eva run --dataset evals/suite.yaml --target http://localhost:8000/chat
eva run --dataset evals/suite.yaml --concurrency 4
eva run --dataset evals/suite.yaml --no-tui          # CI mode (plain output)
```

### Dataset YAML structure

```yaml
name: refund_suite
target: http://localhost:8000/chat
evaluators:
  - name: contains
    mode: binary
tests:
  - id: test_01
    input: "Refund order 123"
  - id: test_02
    input: "What is my balance?"
    expected_output: "balance"
```

---

## Gateway Server

```bash
eva serve                                            # :8080, contracts/ dir
eva serve --port 9000 --contracts-dir ./contracts
eva serve --reload                                   # dev hot-reload (workers=1)
eva serve --workers 4                                # production
```

Health probe: `curl http://localhost:8080/health`

---

## Observe: Runs

```bash
eva runs list                                        # recent runs
eva runs list --dataset refund_suite --status fail
eva runs list --limit 20
eva runs show --run-id <id>                          # details + invocations
```

---

## Observe: Invocations

```bash
eva invocations show --id <invocation-id>            # full detail
```

Shows: request/response artifacts, evaluator scores, tool calls, token usage.

---

## Compare Runs

```bash
eva compare --left <run-id> --right <run-id>         # side-by-side diff
```

Compares: models, invocation count, cost, per-evaluator pass rates.

---

## Failures

```bash
eva failures list                                    # all recent failures
eva failures list --evaluator no_pii
eva failures list --model gpt-4o --dataset refund_suite
```

---

## Drift Detection

```bash
eva drift report --dataset refund_suite --target http://localhost:8000/chat
eva drift report --dataset refund_suite --target http://... --window 20 --threshold 0.05
```

---

## Annotations (Human Review)

```bash
eva annotate add --invocation <id> --label correct --score 1.0 --notes "looks good"
eva annotate list --invocation <id>

eva review queue                                     # pending review items
eva review queue --failed-only
```

---

## Usage & Cost

```bash
eva usage report
eva usage report --dataset refund_suite
```

---

## Common Tips

| Symptom | Fix |
|---------|-----|
| `eva run` exit 1 | Some tests failed — check output |
| Contract not found on serve | Place YAML in `--contracts-dir` (default `contracts/`) |
| DB in wrong location | Pass `--db ./path/state.db` to any observe command |
| Regression detected | `eva contract diff` exits 1 when regressions exist |
| No annotations shown | Invocation ID must match exactly |
