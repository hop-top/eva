# Benchmarks

Read when comparing models on a dataset that grows over time. A result for (model, case) stands forever, so a new case costs one call per model on that case only.

## Build the dataset

A directory with `dataset.yaml` (`name`, `target`, `evaluators`, `append_only: true`) and one or more `*.jsonl` case files. Every case needs `metadata.source`, `metadata.licence`, `metadata.added` (ISO date) and `metadata.origin` (`import`|`failure`|`handwritten`); `metadata.category` adds per-category figures.

```bash
eva dataset import mmlupro --into bench/ --n 50 --seed 0
eva dataset add bench/ --from new-cases.jsonl --file reasoning.jsonl --dry-run
eva dataset lock bench/
eva dataset check bench/
```

- Cases are appended, never edited. A wrong case stays and a new case names it with `supersedes: <old id>`; the old one drops out of scoring.
- `eva dataset check` exits `3` on an edited, removed or unrecorded case; `eva run` does the same check first. After appending by hand, `eva dataset lock` records the new cases.
- `eva dataset import` sources: `babilong`, `mmlupro`, `summedits`, `humanevalplus`, `mbppplus`, `naturalplan`. A larger `--n` with the same `--seed` only appends.

## Run only what is missing

```bash
eva run --dataset bench/ --provider openai --base-url http://localhost:12000/v1 \
  --model my-model --missing --dry-run
eva run --dataset bench/ --provider openai --model my-model --missing --category math --limit 20 --no-tui
```

- `--missing` runs the cases this model has no stored result for at the case's current hash. Nothing missing: exit `0`.
- The model is identified as `provider:model`, the URL for a URL target, or `--target-id`; the base URL is not part of it, so results move between machines.
- Not recorded, so retried next time: cases whose target call failed, and cases no evaluator applied to.

## Read and move results

```bash
eva results list --dataset bench --target openai:my-model --status fail --format json
eva results compare --dataset bench --left-target openai:a --right-target openai:b --dataset-file bench/ --format json
eva results export --dataset bench --dir results/
eva results import results/
```

- `compare` counts only cases both models answered at the same case hash and lists the ids only one side passed. `--dataset-file` adds per-category figures and drops superseded cases.
- Exported JSONL is the durable copy: commit it, import it on another machine. Import keeps the earlier result on a conflict and exits `1` to report it.
- Per-category pass counts also appear in `eva run` output, `eva runs show --run-id <id>` and `eva compare`; `--since YYYY-MM-DD` adds accuracy on cases added since that date.
