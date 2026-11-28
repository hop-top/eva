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
  - name: refusal
    refusal_mode: forbid
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
- `evaluators`: each item has `name`, optional `mode`, optional `min_score`, plus the evaluator's own keys at the same level.
- `mode` is the pass mode only: `binary` (default; the score must reach `min_score`, default `1.0`), `threshold`, or `warn` (recorded, never fails). An evaluator's own setting has its own key: `refusal_mode` (`forbid`|`require`) for `refusal`, `count_mode` (`sentence`|`paragraph`) for `sentence_paragraph_count`.
- `request_schema`, `retry_policy` and `prompt_field` apply to the gateway only. `prompt_field` names the top-level request body key that holds the prompt for judge evaluators.

## Evaluators

- Text and structure: `contains` (`substring`), `regex` (`pattern`), `last_paragraph_regex`, `equals` (`expected`), `exact_match`, `final_answer`, `json_schema_valid` (`schema`), `json_path`, `word_count` (`min`, `max`), `sentence_paragraph_count`, `markdown_structure`, `forbidden_phrases` (`banlist`), `citation`, `no_pii`, `refusal`, `language`, `mood`.
- `key_facts`: required facts (each a string or a list of accepted variants) and forbidden strings per case under `metadata.key_facts`, or `required`/`forbidden` in the contract. Score is found/total; `threshold` sets the pass bar.
- `status_code` (alias `exit_code`; `expected`): a recorded command's exit status.
- Code: `code_tests` runs extracted code in an isolated subprocess against `tests` (asserts) or `stdio` pairs; `require_isolation: true` scores 0 where no OS-level sandbox exists.
- Tool calls: `tool_call_match` compares a chat target's logged tool calls with `metadata.expected_calls` (`match`: `single`, `first`, `ordered`, `parallel`, `none`).
- Instruction following: `ifeval_check` needs `pip install "hop-top-eva[ifeval]"` and a one-time `eva data fetch`.
- Judge, model scored: `relevance`, `hallucination`, `tone` (`expected_tone`), `task_completion`, `safety`, `tool_correctness`, `geval`, and the `rag:*` and `content:*` families.
- `field: <key>` scopes `contains`, `regex`, `equals` and `status_code` to one top-level key of a JSON object input. A missing key or a non-object input scores 0.0.

A bad value for any evaluator key fails `validate` and every run with `evaluator 'X': <key> ...`.

## Exit codes of a recorded command

To gate on a command's exit status and output together, save both in one JSON object (`{"exit_code": 0, "stdout": "..."}`) and give each evaluator a `field`.
