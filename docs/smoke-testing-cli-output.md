# Cookbook: Smoke-Testing CLI Output with an Eva Contract

End-to-end worked example: gate a CLI's behaviour in CI by evaluating its
captured output against an Eva contract with `eva run --contract --input`. No
live agent, no Eva server, no flake.

The example uses [`tlc`](https://github.com/hop-top/tlc) as the CLI under
test (`tlc task create`), but the recipe applies to any CLI that prints text
or JSON.

> **Scope.** This cookbook uses the `regex` and `contains` evaluators, which
> work against arbitrary text. The `exit_code` and `field:`-scoped forms,
> which read fields out of a JSON object, are covered in
> [Contracts for CLI output](contract-yaml-reference.md#contracts-for-cli-output)
> and the [evaluators reference](evaluators-reference.md).

---

## What you need

| Tool | Purpose |
|------|---------|
| `tlc` | CLI under test |
| `eva` | Contract gate (`eva run --contract --input`) |

---

## 1 — The contract

```yaml
# contracts/tlc_task_create.yaml
name: tlc_task_create_smoke
provider: tlc
evaluators:
  - name: regex            # task ID was emitted
    pattern: 'Created task T-[0-9]{4}'

  - name: contains         # the title was echoed back
    substring: 'smoke test task'
```

Both evaluators run against the whole input text. Contract mode reads only
`name` and `evaluators`; `provider` is required by the contract schema but
is never contacted, and `request_schema` is not consulted (see
[Contracts for CLI output](contract-yaml-reference.md#contracts-for-cli-output)).

---

## 2 — Capture the CLI output

```bash
tlc task create "smoke test task" > output.txt
```

Exit code `0`. `output.txt` holds what the CLI printed:

```text
Created task T-0007: smoke test task
```

---

## 3 — Gate on the contract

```bash
eva run --contract contracts/tlc_task_create.yaml --input output.txt --format text
```

```text
Contract: tlc_task_create_smoke
  [PASS] regex (mode=binary, score=1.00, 0ms)
  [PASS] contains (mode=binary, score=1.00, 0ms)
PASSED  2/2 evaluators  (0ms)
```

Exit code `0`. Without `--format`, the report is JSON in CI (non-TTY) and
text in a terminal.

The input can also come from a pipe (`--input -`):

```bash
tlc task create "smoke test task" | eva run --contract contracts/tlc_task_create.yaml --input -
```

Exit code `0`, same report as JSON. The pipeline's exit status is the one
of `eva`; capture to a file first (step 2) when the CLI's own exit status
must fail the job too.

* Exit `0`: every evaluator passed; safe to merge.
* Exit `1`: at least one evaluator failed; the report goes to stderr.
* Exit `2`: malformed contract, or missing or unreadable input file.

---

## 4 — What a failing contract looks like

Change the pattern to `Created task X-[0-9]{4}` and run again:

```bash
eva run --contract contracts/tlc_task_create.yaml --input output.txt --format text
```

```text
Contract: tlc_task_create_smoke
  [FAIL] regex (mode=binary, score=0.00, 0ms)
    reason: Pattern 'Created task X-[0-9]{4}' not found in response
  [PASS] contains (mode=binary, score=1.00, 0ms)
FAILED  1/2 evaluators  (0ms)
```

Exit code `1`, with the report on stderr. A missing input file prints
`Error: Input file not found: nope.txt` and exits `2`.

With `--format json`, the report on stderr is:

```json
{
  "contract": "tlc_task_create_smoke",
  "passed": false,
  "duration_ms": 0,
  "evaluators": [
    {
      "name": "regex",
      "mode": "binary",
      "min_score": 1.0,
      "score": 0.0,
      "passed": false,
      "reason": "Pattern 'Created task X-[0-9]{4}' not found in response",
      "duration_ms": 0
    },
    {
      "name": "contains",
      "mode": "binary",
      "min_score": 1.0,
      "score": 1.0,
      "passed": true,
      "reason": null,
      "duration_ms": 0
    }
  ],
  "skipped": [],
  "skipped_judge": []
}
```

---

## 5 — Wire into CI

```yaml
- name: Smoke test tlc CLI
  run: |
    tlc task create "smoke test task" > output.txt
    eva run \
      --contract contracts/tlc_task_create.yaml \
      --input output.txt \
      --format json
```

The step fails when either command exits non-zero. Pipe stderr to your CI
annotation step to surface the failing evaluator's `reason`.

---

## Why this pattern

* **Hermetic** — the gate needs no Eva server and no LLM call.
* **Cheap** — millisecond gate; no API budget.
* **Drift-detecting** — change the CLI's output format and the contract
  fails. Update the contract and commit it.
* **Reusable** — drop the same recipe on any CLI: replace the command and
  the patterns in the contract.

---

## Related

* [CLI reference: `eva run --contract`](cli-reference.md#standalone-contract-mode)
* [Contracts for CLI output](contract-yaml-reference.md#contracts-for-cli-output)
* [Evaluators reference: regex, contains](evaluators-reference.md)
* [Architecture: standalone CLI vs gateway](architecture.md)
