# Dataset Importers

`eva dataset import` samples cases from public benchmark sets and appends them
to an [append-only dataset](dataset-reference.md#append-only-datasets). The
sample is seeded and repeatable, a larger sample only appends, and every case
carries provenance, so results already stored for earlier cases stay valid.

```bash
mkdir pool && printf 'name: pool\ntarget: {provider: openai, base_url: http://localhost:8080/v1, model: m}\nappend_only: true\nevaluators:\n  - {name: final_answer}\n  - {name: code_tests, timeout: 30}\n' > pool/dataset.yaml
eva dataset import mmlupro --into pool --n 20 --seed 7 --dry-run
eva dataset import mmlupro --into pool --n 20 --seed 7     # appends 20
eva dataset import mmlupro --into pool --n 50 --seed 7     # appends exactly 30 more
eva dataset import mmlupro --into pool --n 50 --seed 7     # no-op
```

## Sources

| Source | Upstream | Licence stamped on cases | Category | Evaluator |
|---|---|---|---|---|
| `babilong` | `RMT-team/babilong`, configs `8k` and `16k`, splits `qa1`-`qa5` | Apache-2.0; BSD (bAbI) | `long-context` | `final_answer` |
| `mmlupro` | `TIGER-Lab/MMLU-Pro`, `test` | MIT | `reasoning` | `final_answer` |
| `summedits` | `Salesforce/summedits`, `train` | CC-BY-4.0 | `summarizing` | `final_answer` |
| `humanevalplus` | `evalplus/humanevalplus`, `test` | Apache-2.0 | `coding` | `code_tests` (`timeout: 30`) |
| `mbppplus` | `evalplus/mbppplus`, `test` | Apache-2.0 | `coding` | `code_tests` (`timeout: 30`) |
| `naturalplan` | `google-deepmind/natural-plan`, `data/calendar_scheduling.json` | CC-BY-4.0 | `executive-assistant` | `final_answer` |
| `zebralogic` | `WildEval/ZebraLogic`, `mc_mode` | none: **refused** | - | - |

Where each licence was read (2026-11-27):

- MMLU-Pro, SummEdits, HumanEval+, MBPP+: the `license` field of the Hugging
  Face dataset card (`mit`, `cc-by-4.0`, `apache-2.0`, `apache-2.0`). The
  importer re-reads it on every run and refuses to import when it no longer
  matches.
- BABILong: the card has no `license` field; its "License" section states the
  code is Apache-2.0 and that the data comes from PG-19 (Apache-2.0) and bAbI
  (BSD).
- Natural Plan: the repository README states software is Apache-2.0 and all
  other materials, which include the data, CC-BY.
- ZebraLogic: the dataset card states no licence and the repository has no
  licence file, so it cannot be imported. `eva dataset import zebralogic`
  exits `2`. It becomes importable once an upstream licence is confirmed.

Sets under non-commercial licences are not offered: a case's licence is
recorded so that such a set never lands in a dataset that is redistributed.

### What each case looks like

| Source | `input` | `expected_output` / `tests` | Extra `metadata` |
|---|---|---|---|
| `babilong` | the long text, the question, "answer with a single word" and a `Final answer: <word>` instruction | `expected_output`: the target word | `context` (`8k`/`16k`), `task` (`qa1`-`qa5`) |
| `mmlupro` | question, lettered options (A-J), `Final answer: <letter>` instruction | `expected_output`: the answer letter | `subject`: upstream category |
| `summedits` | document, summary, `Final answer: consistent` / `inconsistent` instruction | `expected_output`: `consistent` or `inconsistent` | `domain` |
| `humanevalplus` | the function prompt, "reply with one python block" | `tests`: the EvalPlus test plus `check(entry_point)` | - |
| `mbppplus` | the task text, required function name and the first assertion, same reply instruction | `tests`: the EvalPlus test | - |
| `naturalplan` | the 0-shot prompt plus a `Final answer: <Day>, <HH:MM> - <HH:MM>` instruction | `expected_output`: the slot of the golden plan | `people`, `days` |

Always set: `category` (a per-category score key), `source`, `licence`,
`added` (the import date) and `origin: import`.

`source` reads `<upstream>:<config>/<split>#<row>@<revision>` for Hugging Face
sets (`<revision>` is the first 12 characters of the dataset repository's head
commit when the rows were read) and `google-deepmind/natural-plan:calendar_scheduling#<key>@<commit>`
for Natural Plan. `metadata` is not part of the case hash, so a changed
revision never makes a re-import conflict.

### Case ids

Ids come from the upstream row identity, never from the position in the
sample: `babilong-<config>-<split>-<row>` (e.g. `babilong-8k-qa1-013`),
`mmlupro-<question_id>`, `summedits-<id>`, `humanevalplus-<NNN>` (task number),
`mbppplus-<NNNN>` (task id), `naturalplan-<example key>`. A row keeps its id
and its case hash whatever seed or size selected it.

### Admission rules

- `babilong`: the ten cells (`8k`, `16k` x `qa1`-`qa5`) are visited in turn.
  Contexts longer than 16k are not offered.
- `summedits`: consistent and inconsistent cases alternate; documents longer
  than 12,000 characters are skipped.
- `humanevalplus`, `mbppplus`: a case is admitted only when the dataset's own
  reference solution passes the case's `tests` under the `code_tests`
  evaluator, run the way a model answer is run. Rows whose test code is
  longer than 60,000 (HumanEval+) or 30,000 (MBPP+) characters are skipped,
  and a viewer-truncated row is skipped. The EvalPlus tests import numpy only
  to compare floats; eva's `code_tests` environment has no numpy, so the
  `import numpy as np` line is replaced by a small stand-in with the same
  `allclose` semantics used there. Some references need several seconds:
  set `timeout: 30` on `code_tests`.
- `naturalplan`: cases are spread evenly over the number of attendees
  (2 to 7); an entry whose golden plan has no time slot is skipped.

The coding importers **execute the upstream reference solutions** on this
machine to verify them. `code_tests` isolation is hygiene, not a sandbox: see
[the security note](evaluators-reference.md#code_tests).

## Sampling

Each source defines one deterministic order over its upstream rows. Rows are
ranked by `sha256("<source>:<cell>:<seed>:<row>")`; stratified sources
(`babilong` cells, `summedits` labels, `naturalplan` attendee counts) take
turns between strata, each with its own ranking. `--n N` takes the first `N`
admitted cases of that order. The order depends on the seed and the rows only,
so:

- same seed and source: same cases in the same order;
- `--n 20` then `--n 50` on one dataset appends exactly 30 cases and leaves
  the first 20 lines and ledger entries byte-identical;
- a different seed gives a different order over the same case ids.

Cases are written through the same path as `eva dataset add`: an id already
present with the same content hash is skipped, so a second identical import
changes nothing. A case whose id is present with different content (an
upstream edit) is refused, exit `3`, and nothing is written. Cases are
appended to `<source>.jsonl` in the dataset directory (`--file` to change)
and recorded in `dataset.lock.json`.

## `eva dataset import`

```text
eva dataset import SOURCE --into DIR [--n N] [--seed S] [--file NAME.jsonl]
                   [--dry-run] [--format text|json]
```

| Option | Meaning |
|---|---|
| `SOURCE` | `babilong`, `mmlupro`, `summedits`, `humanevalplus`, `mbppplus`, `naturalplan` |
| `--into DIR` | Existing directory dataset with `append_only: true` (manifest `dataset.yaml`) |
| `--n N` | Cases wanted (default 20). Fewer are written when the source has fewer admissible rows |
| `--seed S` | Sampling seed, any text (default `0`) |
| `--file NAME.jsonl` | Target file inside `DIR` (default `<SOURCE>.jsonl`) |
| `--dry-run` | Fetch and report what would be added; write nothing |
| `--format` | `text` (default) or `json` |

JSON: `ok, dry_run, source, seed, requested, sampled, revision, added,
skipped, problems` (each problem `{code, id, message}` as for
`eva dataset add`).

### Exit codes

- `0`: imported, or nothing new to add.
- `1`: upstream unreachable, rate limited past the retries, or an unusable
  response. Nothing is written.
- `2`: usage or bad input: unknown source, `--format` invalid, `--n` below 1,
  directory missing or not append-only, source refused (no verified licence,
  or the card's licence changed).
- `3`: a case conflicts with or fails the dataset's integrity rules
  (same id with different content, invalid case). Nothing is written.

### Fetching

Standard library only. Rows come one at a time from the Hugging Face dataset
viewer rows API, the repository head from the Hub API (Natural Plan: the git
smart-HTTP ref advertisement, then one raw file at that commit). Requests are
spaced by at least 0.5 s, identify themselves as `eva-dataset-importer`, and
429/5xx/connection errors are retried with backoff (up to five tries; a
`Retry-After` header is honoured). Cases are written only after every fetch
and check has succeeded.

## Choosing evaluators

```yaml
evaluators:
  - {name: final_answer}          # answer cases: reads the last "Final answer:" line
  - {name: code_tests, timeout: 30}   # coding cases: runs the model's code block + tests
```

An evaluator that needs a case field is skipped for cases without it, so one
dataset can hold every source. `final_answer` compares the last
`Final answer: ...` line of the reply with `expected_output` after
normalisation (case, surrounding punctuation and markup, numbers); the
imported prompts end with the instruction for that line.
