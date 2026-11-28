# Contract YAML

Read when writing or editing a contract. Validate with `eva contract validate <file>`.

```yaml
name: refund_policy
provider: billing-agent
evaluators:
  - name: contains
    substring: refund
  - name: regex
    pattern: 'ORD-[0-9]+'
    field: stdout
  - name: relevance
    mode: threshold
    min_score: 0.7
prompt_field: question
retry_policy:
  max_retries: 2
  hint: State the refund id.
```

## Fields

- `name` and `provider` are required. `provider` is never contacted in standalone mode.
- `evaluators`: each item has `name`, optional `mode`, optional `min_score`, plus evaluator fields at the same level.
- `mode`: `binary` (default, score must reach `min_score`), `threshold`, or `warn` (recorded, never fails).
- `request_schema`, `retry_policy` and `prompt_field` apply to the gateway only. `prompt_field` names the top-level request body key that holds the prompt for judge evaluators.

## Evaluators

- Deterministic: `contains` (`substring`), `regex` (`pattern`; not `regex_match`), `json_schema_valid` (`schema`), `no_pii`, `equals` (`expected`), `status_code` (alias `exit_code`; `expected`), `word_count` (`min`, `max`), `forbidden_phrases` (`banlist`), `json_path`, `refusal`, `language`.
- Judge, model scored: `relevance`, `hallucination`, `tone` (`expected_tone`), `task_completion`, `safety`, `tool_correctness`.
- `field: <key>` scopes `contains`, `regex`, `equals` and `status_code` to one top-level key of a JSON object input. No nested paths. A missing key or a non-object input scores 0.0.

## Exit codes of a recorded command

To gate on a command's exit status and output together, save both in one JSON object (`{"exit_code": 0, "stdout": "..."}`) and give each evaluator a `field`.
