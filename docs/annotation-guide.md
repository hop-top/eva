# Annotation Guide

Human review layer on top of automated evaluations.  Lets reviewers attach
labels, corrected outputs, and quality scores to individual invocations; surfaces
evaluation failures for triage.

---

## Concepts

| Term | Meaning |
|------|---------|
| **Invocation** | Single LLM call recorded by Eva (has a UUID). |
| **Annotation** | Human judgement attached to one invocation. |
| **Evaluator result** | Automated pass/fail score produced during a run. |
| **Review queue** | Set of invocations needing human attention. |

---

## Adding an annotation

```
eva annotate add --invocation <id> [options]
```

Options:

| Flag | Description | Default |
|------|-------------|---------|
| `--invocation` | Invocation UUID (required) | — |
| `--label` | Short label, e.g. `correct`, `wrong`, `partial` | — |
| `--score` | Float 0.0–1.0 quality score | — |
| `--notes` | Free-text commentary | — |
| `--reviewer` | Reviewer identifier | `human` |
| `--db` | SQLite DB path (overrides `eva.yaml`) | `.eva/state.db` |

Pseudocode — label an invocation as correct with a note:

```
eva annotate add \
  --invocation <uuid> \
  --label correct \
  --score 1.0 \
  --notes "Output matched expected intent exactly." \
  --reviewer alice
```

Multiple annotations can be added to the same invocation; each gets its own
`annotation_id`.

---

## Listing annotations for an invocation

```
eva annotate list --invocation <id> [--db <path>]
```

Prints a table with: annotation ID, reviewer, label, score, notes, creation time.
Returns an empty-queue notice if no annotations exist yet.

---

## The review queue

```
eva review queue [--failed-only] [--db <path>]
```

Shows invocations that need human attention:

- **No annotation yet** — any unannotated invocation.
- **Has a failing evaluator result** — at least one automated check failed.

Columns shown:

| Column | Meaning |
|--------|---------|
| Invocation | Truncated ID |
| Status | Pass / fail / upstream_error |
| Target | Agent URL |
| Evaluator Scores | `<name>: <score> (pass|fail)` per evaluator |
| Human Label | Label + score from most recent annotation |
| Flags | `FAIL` / `UNREVIEWED` / ok |

### `--failed-only`

Restrict output to invocations where at least one evaluator result is `passed=False`.
Useful for targeted triage when the full queue is large.

---

## Evaluator-vs-human comparison

The **Evaluator Scores** column shows automated judgements; **Human Label** shows
the reviewer's label and score for the same invocation.

When an evaluator marks an invocation as `fail` but the reviewer labels it
`correct`, the discrepancy is immediately visible in the same row.  This is the
primary signal for:

- Calibrating evaluator thresholds.
- Identifying systematic evaluator false-positives.
- Building correction datasets from `--label correct` annotations.

Workflow:

```
# 1. Open review queue filtered to failures
eva review queue --failed-only

# 2. Inspect a specific invocation detail (shows full request/response)
#    Use the invocation ID from the queue table

# 3. Add your judgement
eva annotate add --invocation <id> --label correct --score 1.0 \
    --notes "Evaluator was too strict; output is acceptable."

# 4. Re-run queue — invocation now shows human label alongside evaluator score
eva review queue --failed-only
```

---

## Storage

Annotations are stored in the same SQLite database as invocations
(default: `.eva/state.db`, table `annotationrecord`).  Pass `--db <path>` to
any command to target a non-default database.
