# Cookbook: Smoke-Testing a CLI with `tlc flow test` + Eva

End-to-end worked example: gate a CLI's behaviour in CI by recording its
output once, then evaluating that recording against an Eva contract on every
run. No live agent, no Eva server, no flake.

The example uses [`tlc`](https://github.com/hop-top/tlc) as the CLI under
test (`tlc task create`), but the recipe applies to any CLI that produces
structured output.

> **Scope.** This cookbook only uses evaluators that already exist on
> `eva` `main` today: `regex` and `contains`. Both work against arbitrary
> response strings and need no flow-step routing. A follow-up cookbook
> (`hop-top/eva#flow-exec-evaluators`) covers the structured
> `status_code` / `equals` evaluators that pull typed fields out of a
> step's JSON output.

---

## What you need

| Tool | Purpose |
|------|---------|
| `tlc` | CLI under test; provides `flow test` record/replay sandbox |
| `eva` | Standalone contract gate (`eva run --contract --input`) |

---

## 1 — The flow YAML (owned by `tlc`)

Create a single-step flow that runs `tlc task create`. The canonical example
file lives in the [`tlc` repo](https://github.com/hop-top/tlc) under
`hop-top/tlc#flow-exec-step` (T-0730 owns it).

```yaml
# .tlc/flows/task-create-smoke.yaml
flow_id: "flow:task-create-smoke:1.0"
name: task-create-smoke
version: "1.0"
entry_step: create
steps:
  create:
    step_id: create
    type: exec
    command: tlc
    args: [task, create, "smoke test task"]
    capture: [exit_code, stdout, stderr]
```

`tlc flow test` records this step's output as a cassette under
`<flowDir>/fixtures/<flowName>/<run-name>/` and replays it deterministically
on later runs.

---

## 2 — The Eva contract

```yaml
# contracts/tlc_task_create.yaml
name: tlc_task_create_smoke
provider: tlc
evaluators:
  - name: regex            # task ID was emitted
    pattern: 'Created task T-[0-9]{4}'

  - name: contains         # initial state is TODO
    substring: 'TODO'
```

Both evaluators run against the captured `stdout` string — no schema
discriminator, no field routing. Pipe the recording's `stdout` field into
`eva run --input` (step 5 below).

---

## 3 — Record the flow (once, locally)

```bash
tlc flow test .tlc/flows/task-create-smoke.yaml happy-path --record
```

Cassettes are written under
`.tlc/flows/fixtures/task-create-smoke/happy-path/`. Commit that directory.

---

## 4 — Replay the flow (CI: deterministic)

```bash
tlc flow test .tlc/flows/task-create-smoke.yaml happy-path
```

Without `--record`, `tlc flow test` replays from the cassette directory it
discovers under `fixtures/<flowName>/`. No live `tlc` process is spawned;
exit code 2 means a cassette miss.

---

## 5 — Gate on the contract (CI: hermetic)

Pull the recorded `stdout` out of the cassette and feed it to `eva run`. The
cassette layout is owned by `tlc`/`xrr`; this snippet assumes a JSON
recording with a `stdout` field — adapt the `jq` path to whatever format
your cassette uses.

```bash
jq -r '.stdout' \
  .tlc/flows/fixtures/task-create-smoke/happy-path/exec.json \
  > /tmp/task-create-stdout.txt

eva run \
  --contract contracts/tlc_task_create.yaml \
  --input /tmp/task-create-stdout.txt \
  --format json
```

* Exit `0`: every evaluator passed; safe to merge.
* Exit `1`: at least one evaluator failed; report (JSON) goes to stderr —
  pipe it to your CI annotation step.
* Exit `2`: malformed contract or missing input file.

### Wire into GitHub Actions

```yaml
- name: Smoke test tlc CLI
  run: |
    tlc flow test .tlc/flows/task-create-smoke.yaml happy-path
    jq -r '.stdout' \
      .tlc/flows/fixtures/task-create-smoke/happy-path/exec.json \
      > /tmp/stdout.txt
    eva run \
      --contract contracts/tlc_task_create.yaml \
      --input /tmp/stdout.txt \
      --format json \
      || (echo "::error::Contract violated"; exit 1)
```

---

## Why this pattern

* **Hermetic** — no live `tlc` process, no Eva server, no LLM call.
* **Cheap** — millisecond gate; no API budget.
* **Drift-detecting** — change the CLI's output format and the contract
  fails. Update the cassette, update the contract, commit both.
* **Reusable** — drop the same recipe on any CLI: replace the command in
  the flow YAML and the patterns in the contract.

---

## Related

* [CLI reference: `eva run --contract`](cli-reference.md#standalone-contract-mode)
* [Evaluators reference: regex, contains](evaluators-reference.md)
* [Architecture: standalone CLI vs gateway](architecture.md)
* `hop-top/tlc#flow-exec-step` — owns the canonical flow exec step + sample YAML
* `hop-top/eva#flow-exec-evaluators` — sibling track adding `status_code`,
  `exit_code`, `equals` for typed-field assertions against step outputs
