# Drift Detection Guide

---

## What Is Drift?

Drift: score distribution shift for a given evaluator over time. Caused by:

- Model updates changing response quality or format.
- Prompt engineering changes.
- Data distribution changes in production inputs.
- Gradual degradation (model staling, infra issues).

Eva measures drift by comparing the most recent run's score against the mean of
all earlier runs in a window, per evaluator.

---

## `eva drift report`

```
eva drift report [OPTIONS]
```

### Flags

| Flag | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `--dataset` | str | yes | — | Dataset name to analyse |
| `--target` | str | yes | — | Target agent URL |
| `--window` | int | no | `10` | Number of recent runs to compare |
| `--threshold` | float | no | `0.1` | Score delta that triggers UP/DOWN |
| `--db` | str | no | `.eva/state.db` | Path to SQLite DB file |

### Example

```sh
eva drift report \
  --dataset my-eval-suite \
  --target http://agent:8000/ \
  --window 20 \
  --threshold 0.05
```

---

## Output

Rich table printed to stdout:

```
Drift Report — my-eval-suite → http://agent:8000/ (last 20 runs)
┌───────────────────┬──────────┬─────────┬─────────┬────────┐
│ Evaluator         │ Baseline │ Current │ Delta   │ Trend  │
├───────────────────┼──────────┼─────────┼─────────┼────────┤
│ contains          │ 0.9200   │ 0.7500  │ -0.1700 │ ↓ down │
│ json_schema_valid │ 1.0000   │ 1.0000  │ +0.0000 │ stable │
│ no_pii            │ 0.8800   │ 0.9100  │ +0.0300 │ stable │
└───────────────────┴──────────┴─────────┴─────────┴────────┘
```

### Column Definitions

| Column | Description |
|--------|-------------|
| `Evaluator` | Evaluator name |
| `Baseline` | Mean score of all runs except the most recent |
| `Current` | Score from the most recent run |
| `Delta` | `current − baseline` |
| `Trend` | `↑ up` / `↓ down` / `— stable` |

`Baseline` shown as `—` when fewer than 2 runs exist (no comparison possible).

---

## Trend Calculation

```
delta = current_score - mean(earlier_scores)

if delta > threshold:   trend = UP
elif delta < -threshold: trend = DOWN
else:                    trend = STABLE
```

Default `threshold = 0.1` (10% score change triggers UP or DOWN).

Runs sorted oldest → newest internally; order of input does not matter.

---

## Storage

Reads from SQLite via `SqliteStorage`. Default DB path: `.eva/state.db`.

Runs are written by `eva run` at the end of each evaluation session.
`drift report` reads runs matching the given `dataset` + `target` pair.

Override DB path:

```sh
eva drift report --dataset ... --target ... --db /path/to/state.db
```

Or set `EVA_STORAGE=sqlite:////path/to/state.db` in environment (read by
`eva run`; drift report uses `--db` flag directly).

---

## Use Cases

### Catching Model Regressions

Run `eva run` in CI after each model update. Run `eva drift report` with
`--window 5 --threshold 0.05` to flag small regressions early.

### Compliance Audits

Historical window: `--window 100` across a quarter of production runs.
Tight threshold: `--threshold 0.02` for high-confidence evaluators.

### Canary Deployments

Compare `--target http://canary/` vs `--target http://production/` using
identical datasets.

---

## Notes

- No data stored by `drift report` itself — read-only operation.
- Evaluators with only one run always show `Trend: stable` (no baseline).
- UP trend is not necessarily bad (score improving); DOWN trend warrants
  investigation.
