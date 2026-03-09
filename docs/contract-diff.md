# eva contract diff — Command Reference

Detect regressions between two contract YAML versions.

---

## Usage

```
eva contract diff CONTRACT_A CONTRACT_B
```

| Argument     | Description                     |
|--------------|---------------------------------|
| `CONTRACT_A` | Path to base (old) contract.    |
| `CONTRACT_B` | Path to new contract.           |

---

## What it checks

| Change type          | Regression? | Description                              |
|----------------------|-------------|------------------------------------------|
| Evaluator removed    | Yes         | Old evaluator missing in new contract.   |
| Threshold lowered    | Yes         | `min_score` decreased for an evaluator.  |
| Evaluator added      | No          | New evaluator in updated contract.       |
| Threshold raised     | No          | `min_score` increased (stricter).        |
| No changes           | No          | Contracts identical.                     |

---

## Exit codes

| Code | Meaning                                         |
|------|-------------------------------------------------|
| `0`  | No regressions (may have non-breaking changes). |
| `1`  | Regressions found, or invalid contract file.    |

---

## Example output

### No regressions

```
Contract diff: v1.yaml → v2.yaml

  + added     regex
  ↑ tightened contains  min_score 0.80 → 0.90

No regressions.
```

Exit code: `0`

### Regressions found

```
Contract diff: v1.yaml → v2.yaml

  − removed   no_pii
  ↓ loosened  contains  min_score 0.90 → 0.50

Regressions detected.
```

Exit code: `1`

### No changes

```
Contract diff: v1.yaml → v1.yaml

No changes detected.
```

Exit code: `0`

---

## CI integration

Gate PR merges on contract regressions:

```bash
# pseudocode for CI step
eva contract diff contracts/main.yaml contracts/pr.yaml || exit 1
```

Or as a justfile target:

```make
# pseudocode
contract-gate:
    eva contract diff contracts/main.yaml contracts/pr.yaml
```

---

## Errors

| Error                        | Cause                            |
|------------------------------|----------------------------------|
| `Error loading <path>: ...`  | File not found or invalid YAML.  |
| Exit code 1                  | Regressions or load failure.     |

---

## Related commands

- `eva contract validate PATH` — validate a single contract.
- See `docs/config-reference.md` for contract YAML schema.
