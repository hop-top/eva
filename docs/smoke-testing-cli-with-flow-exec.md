# Cookbook: Smoke-Testing a CLI with `tlc flow exec` + Eva

End-to-end worked example: gate a CLI's behaviour in CI by recording its
output once, then evaluating that recording against an Eva contract on every
run. No live agent, no Eva server, no flake.

The example uses [`tlc`](https://github.com/hop-top/tlc) as the CLI under
test (`tlc task create`), but the recipe applies to any CLI that produces
structured output.

> **Status note.** The `status_code`, `exit_code`, and `equals` evaluators
> referenced below land in the same `flow-exec-evaluators` track as this
> cookbook. The standalone `eva run --contract --input` CLI (T-0258) is
> independent and works today — until the new evaluators merge, you can
> exercise the same wiring with `regex`, `contains`, and `json_schema_valid`.

---

## What you need

| Tool | Purpose |
|------|---------|
| `tlc` | CLI under test; provides `flow exec` step + recording mode |
| `eva` | Standalone contract gate (`eva run --contract --input`) |

---

## 1 — The flow YAML (owned by `tlc`)

Create a single-step flow that runs `tlc task create`. The canonical example
file lives in the [`tlc` repo](https://github.com/hop-top/tlc) under
`hop-top/tlc#flow-exec-step` (T-0730 owns it).

```yaml
# .tlc/flows/task-create-smoke.yaml
name: task-create-smoke
steps:
  - id: create
    type: exec
    command: tlc
    args: [task, create, "smoke test task"]
    capture:
      - exit_code
      - stdout
      - stderr
```

`tlc flow exec` records this step's output as a JSON artifact and replays it
deterministically on later runs.

---

## 2 — The Eva contract

```yaml
# contracts/tlc_task_create.yaml
name: tlc_task_create_smoke
provider: tlc
evaluators:
  - name: status_code      # exec succeeded
    expected: 0
    field: exit_code

  - name: regex            # task ID was emitted
    pattern: 'Created task T-[0-9]{4}'
    field: stdout

  - name: contains         # initial state is TODO
    substring: 'TODO'
    field: stdout
```

Each evaluator pulls the field it needs from the recorded JSON artifact.

---

## 3 — Record the flow (once, locally)

```bash
tlc flow record .tlc/flows/task-create-smoke.yaml \
  --out artifacts/task-create-smoke.json
```

`artifacts/task-create-smoke.json` now contains the captured `exit_code`,
`stdout`, `stderr` from the live invocation. Commit it.

---

## 4 — Replay the flow (CI: deterministic)

```bash
tlc flow replay .tlc/flows/task-create-smoke.yaml \
  --recording artifacts/task-create-smoke.json
```

Replay uses the recorded artifact instead of executing `tlc` for real. Use
this when the test only cares that the contract holds, not that the system
under test is live.

---

## 5 — Gate on the contract (CI: hermetic)

```bash
eva run \
  --contract contracts/tlc_task_create.yaml \
  --input artifacts/task-create-smoke.json \
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
    eva run \
      --contract contracts/tlc_task_create.yaml \
      --input artifacts/task-create-smoke.json \
      --format json \
      || (echo "::error::Contract violated"; exit 1)
```

---

## Why this pattern

* **Hermetic** — no live `tlc` process, no Eva server, no LLM call.
* **Cheap** — millisecond gate; no API budget.
* **Drift-detecting** — change the CLI's output format and the contract
  fails. Update the recording, update the contract, commit both.
* **Reusable** — drop the same recipe on any CLI: replace the command in
  the flow YAML and the field paths in the contract.

---

## Related

* [CLI reference: `eva run --contract`](cli-reference.md#standalone-contract-mode)
* [Evaluators reference: status_code, exit_code, equals, regex, contains](evaluators-reference.md)
* [Architecture: standalone CLI vs gateway](architecture.md)
* `hop-top/tlc#flow-exec-step` — owns the canonical flow exec step + sample YAML
* `hop-top/eva#flow-exec-evaluators` — track that introduced these evaluators + the standalone CLI
