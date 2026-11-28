# Built-in Evaluators Reference — Eva

Evaluators analyze an agent's response and return a **Score** (0.0 to 1.0). In Phase 1, Eva includes a set of **Tier 1 (Deterministic)** evaluators that run locally and do not require LLM calls.

---

## Tool-call log

When a chat-target case offers `tools` (see
[dataset-reference.md](dataset-reference.md#tool-definitions-per-case)),
each tool call in the model's reply is recorded in reply order. Evaluators
read the log from `tool_events` in the evaluation context: a list of
`core.events.ToolCallEvent` objects, empty when the reply has no tool call.

| Field | Meaning |
|---|---|
| `tool_name` | Function name the model called. |
| `args` | Parsed arguments, a dict. `{}` when the arguments are not a valid JSON object. |
| `raw_args` | The original argument string when it is not a valid JSON object; `None` otherwise. |
| `step_index` | Position in the reply, starting at 0. Parallel calls keep the order the model returned them in. |

Malformed arguments (truncated JSON, plain text, an empty string, or JSON
that is not an object such as `[1, 2]`) do not fail the case: the call is
recorded with `args == {}` and the exact string in `raw_args`. A valid
`"{}"` also gives `args == {}` but `raw_args is None`, so the two are
distinguishable. The Anthropic provider returns parsed input, so its
`raw_args` is always `None`.

The same calls are stored with the invocation: one tool-call row per call
(`step_index`, `tool_name`, arguments as a `tool_args` artifact), with
`raw_args` exposed on each entry of `tool_calls` in
`core.query.get_invocation_detail`.

---

## `contains`

Checks if the agent's response contains a specific substring.

### Configuration Properties:
| Property | Type | Required | Description |
|---|---|---|---|
| `substring` | `string` | **Yes** | The text to search for. |
| `case_sensitive` | `boolean` | No | Whether the search is case-sensitive. Default: `true`. |
| `field` | `string` | No | Top-level field of a JSON object input to search instead of the whole input. Scores 0.0 if the input is not a JSON object, the field is missing, or its value is not a string. |

### Example Contract Usage:
```yaml
evaluators:
  - name: contains
    substring: "refund"
    case_sensitive: false
```

---

## `regex`

Matches the agent's response against a regular expression pattern.

### Configuration Properties:
| Property | Type | Required | Description |
|---|---|---|---|
| `pattern` | `string` | **Yes** | The regular expression to match. |
| `field` | `string` | No | Top-level field of a JSON object input to match instead of the whole input. Scores 0.0 if the input is not a JSON object, the field is missing, or its value is not a string. |

### Example Contract Usage:
```yaml
evaluators:
  - name: regex
    pattern: "Order #[0-9]{4,6}"
```

---

## `json_schema_valid`

Validates that the agent's response is valid JSON and satisfies a specific JSON Schema.

### Configuration Properties:
| Property | Type | Required | Description |
|---|---|---|---|
| `schema` | `object` | **Yes** | The JSON Schema to validate against. |

### Example Contract Usage:
```yaml
evaluators:
  - name: json_schema_valid
    schema:
      type: object
      required: [status, refund_id]
      properties:
        status: { type: string }
        refund_id: { type: string }
```

---

## `no_pii`

Detects common Personal Identifiable Information (PII) patterns in the agent's response.

### Patterns Detected:
- Email addresses
- Social Security Numbers (SSN)
- Credit card numbers
- Phone numbers

### Example Contract Usage:
```yaml
evaluators:
  - name: no_pii
    mode: binary
```

---

## `status_code` / `exit_code`

Asserts that the `exit_code` (or HTTP-style `status_code`) field matches an
expected integer or falls within an allowed set. `exit_code` is registered as an alias for
`status_code` — both names resolve to the same evaluator class. Use whichever reads more
naturally for your contract; `exit_code` reads as a command's exit status, while `status_code` mirrors HTTP convention.

The evaluator receives the input as a JSON-encoded string. It looks up `exit_code`
first, then falls back to `status_code`. Booleans are rejected (Python's `bool` is an int
subclass — guarded explicitly).

### Configuration Properties:
| Property | Type | Required | Description |
|---|---|---|---|
| `step` | `string` | No | Identifier of the flow step whose output to evaluate. Used by the runner to route the correct payload; metadata only at the evaluator level. |
| `expected` | `int` | One of | Single integer the field must equal exactly. |
| `expected_in` | `list[int]` | One of | Set of acceptable integers. Mutually exclusive with `expected`. |

Exactly one of `expected` or `expected_in` must be provided.

### Example Contract Usage:
```yaml
evaluators:
  - name: status_code
    step: cli-version
    expected: 0
  # exit_code alias — same behavior:
  - name: exit_code
    step: cli-version
    expected: 0
  # allowed set:
  - name: status_code
    step: cli-version
    expected_in: [0, 2]
```

> **Note:** `step_status` was historically referenced in some upstream tlc fixtures
> but never landed in eva. Use `status_code` (or its `exit_code` alias) for exit-code
> checks — those fixtures should be rewritten to point at `status_code`.

---

## `equals`

Generic field-equality evaluator. Asserts that a named field in a JSON step-output payload
equals an expected literal. Supports any JSON-representable type: string, int, float, bool,
list, dict, null.

Type checking is strict (`str` vs `int` is a mismatch) with one exception: int/float
cross-comparison is allowed because JSON numbers may decode either way. Booleans are kept
distinct from integers.

### Configuration Properties:
| Property | Type | Required | Description |
|---|---|---|---|
| `field` | `string` | **Yes** | Name of the field in the step output to compare. |
| `expected` | `any` | **Yes** | Literal value the field must equal. `null` is valid. |
| `step` | `string` | No | Identifier of the flow step whose output to evaluate. |

### Example Contract Usage:
```yaml
evaluators:
  - name: equals
    step: parse-config
    field: log_level
    expected: "info"
  - name: equals
    step: parse-config
    field: retries
    expected: 3
```

---

## `word_count`

Counts whitespace-separated tokens in the response and gates on `min` /
`max`. Used by the newsletter pack to cap drafts at 700 words.

### Configuration Properties:
| Property | Type | Required | Description |
|---|---|---|---|
| `max` | `int` | No | Hard ceiling — fails if word count exceeds this. |
| `min` | `int` | No | Hard floor — fails if word count is below this. |

At least one of `max` / `min` should be set; both unset = always passes.

### Example Contract Usage:
```yaml
evaluators:
  - name: word_count
    mode: binary
    max: 700
```

---

## `last_paragraph_regex`

Like `regex`, but matches only against the LAST non-empty paragraph
(blank-line separated). Used by the newsletter pack to enforce a CTA verb
in the closing paragraph without an early-paragraph match satisfying the
gate.

### Configuration Properties:
| Property | Type | Required | Description |
|---|---|---|---|
| `pattern` | `string` | **Yes** | Regular expression to match against the last paragraph. |
| `case_sensitive` | `boolean` | No | Default `true`. |

### Example Contract Usage:
```yaml
evaluators:
  - name: last_paragraph_regex
    mode: binary
    case_sensitive: false
    pattern: '\b(reply|subscribe|share|join)\b'
```

---

## `exact_match`

Compares the whole response (reasoning stripped) to the test case's
`expected_output` after normalization. This is the name used by sample
datasets such as ben's `gsm8k-sample.yaml`; it is built in.

### Configuration Properties:
| Property | Type | Required | Description |
|---|---|---|---|
| `expected` | `string` | No | Fallback expected value when a case has no `expected_output`. |

Normalization (applies to both sides): trim; unwrap `**bold**`, backticks, quotes, `$`,
`\boxed{}`; drop a trailing period; remove thousands separators (`1,234` = `1234`); casefold;
collapse whitespace. If both sides parse as numbers they compare numerically (`6` = `6.0`).

**Dataset-case evaluator:** reads the case's `expected_output`. A case without one (and no
`expected` config) is not applicable: no result is recorded for it.

```yaml
evaluators:
  - name: exact_match
    mode: binary
tests:
  - id: q1
    input: "What is 3+5-2? Reply with only the number."
    expected_output: "6"
```

---

## `final_answer`

Like `exact_match`, but compares the **last** `Final answer: X` line of the response (also
matches `**Final answer:** X`, `> Final answer: X`, any case). Use it when the model reasons
before answering. No such line scores `0.0` (`no 'Final answer:' line found`).

Same config, normalization and applicability as `exact_match`. Instruct the model in the
prompt to end with `Final answer: <value>`.

---

## `code_tests`

> [!CAUTION]
> **Executes model output** on the machine running eva, in a contained subprocess. The
> containment is hardening, not a security boundary: see [Isolation](#code_tests-isolation) for
> what is and is not contained, and run untrusted workloads inside a container or VM.

Extracts the **last** fenced code block for the language (a block tagged `python`/`py`/`python3`;
else the last untagged block; blocks inside `<think>` reasoning are ignored), appends the case's
tests, runs it, scores `1.0` (exit 0) or `0.0` with the reason (`no python code block found`,
`exit code 1: <stderr tail>`, `execution timeout after Ns`, `memory limit exceeded (>N MB)`,
`process limit exceeded`, `file size limit exceeded (>N MB)`).

<a id="code_tests-isolation"></a>
#### Isolation

Every run, on every platform: separate process in its own process group (killed when the run
ends), fresh temp dir as cwd (deleted after; `HOME`/`TMPDIR` point into it), `python -I`,
minimal environment (`PATH`, `HOME`, `TMPDIR`, `LANG`; no inherited variables), stdin closed,
wall-clock timeout, `RLIMIT_CPU` (timeout + 2s backstop), `RLIMIT_FSIZE` (`max_file_mb`),
core dumps off, and a watchdog that polls `ps` every 250ms and kills the process group above
`memory_mb` of resident memory or 64 processes. Output goes to files, so runaway output is
capped by the file size limit.

| Platform | Extra containment | Verified |
|---|---|---|
| macOS | `sandbox-exec` profile: network denied; `fork` denied; file writes denied outside the temp dir; file contents unreadable under `/Users`, `/Volumes` and the temp roots (interpreter prefixes re-allowed) | yes |
| Linux | `unshare --user --map-root-user --net`: no network, if the kernel allows unprivileged user namespaces (probed once; some distributions restrict this) | not on a Linux host |

What is **not** contained:

- Linux: filesystem reads and writes outside the temp dir are not blocked.
- macOS: reads outside the denied roots (for example `/etc`, `/usr`, `/opt`) are not blocked;
  denying `fork` also stops legitimate `subprocess`/`multiprocessing` use in generated code.
- Memory is capped by polling, not by the kernel (macOS does not apply `RLIMIT_AS`): a fast
  allocation can overshoot the cap briefly. Process count is likewise polled; on Linux a
  process that leaves the process group can outlive the run.
- When no OS layer is available (no `sandbox-exec`, user namespaces disabled, or eva itself
  already inside a sandbox, as in many containers and CI runners), the run falls back to the
  limits above and logs one warning that includes the active layers. Set
  `require_isolation: true` to score such cases `0.0` without running them. Check `core.evaluators._sandbox.isolation_status()` for what is active.
- A kernel or sandbox bug, or an attack by another process of the same user, is out of scope.

### Configuration Properties:
| Property | Type | Required | Description |
|---|---|---|---|
| `language` | `string` | No | Default `python`. Other languages: add a `CodeLanguage` to `CODE_LANGUAGES` in `core/evaluators/code_tests.py`. |
| `timeout` | `number` | No | Seconds, default `10`. `null` rejected. |
| `test_code` | `string` | No | Shared harness appended after each case's tests. |
| `memory_mb` | `integer` | No | Resident-memory cap for the run, default `512`. |
| `max_file_mb` | `integer` | No | Largest file the program may write (including stdout/stderr), default `16`. |
| `require_isolation` | `boolean` | No | Default `false`. When `true` and no OS-level layer (`sandbox-exec`, network namespace) is active on the host, the case scores `0.0` naming what is not active, and the program is not run. When `false`, the run uses the best available layer and logs one warning with `isolation_status()`. |
| `partial` | `boolean` | No | stdin/stdout mode only. Default `false` (all-or-nothing); `true` scores `passed/total`. |

### Test-case fields:
| Field | Type | Description |
|---|---|---|
| `tests` | `string` or `list[string]` | Test code (e.g. `assert` lines), joined by newlines, appended to the extracted code. A case with no `tests` (and no `test_code`) is not applicable: no result recorded. |
| `stdio` | `list[{stdin, expected_stdout}]` | stdin/stdout mode (below). Do not combine with `tests`: a case with both scores `0.0`. |

```yaml
evaluators:
  - name: code_tests
    timeout: 10
tests:
  - id: add
    input: "Write add(a, b) in Python."
    tests: |
      assert add(1, 2) == 3
      assert add(-1, 1) == 0
```

#### stdin/stdout mode

A case with `stdio` runs the extracted program once per pair, with `stdin` as its standard
input, and compares its standard output with `expected_stdout`. Each run has a fresh temp dir
and its own `timeout` (so the worst case is pairs x `timeout`). Comparison ignores trailing
whitespace on every line and at the end of the output (`\r\n` counts as `\n`); leading and
inner whitespace and blank lines between text are significant. Config `test_code` is not used
in this mode.

Score is `1.0` only if every pair passes, else `0.0` (or `passed/total` with `partial: true`).
The reason always carries the count: `passed 2/3; test 3: wrong output (expected '8', got
'7')`. Failures name the pair and say `wrong output`, `runtime error (exit code N: <stderr
tail>)`, `execution timeout after Ns`, or a limit from Isolation; at most three are listed. The
same isolation applies. A pair with no `expected_stdout` scores `0.0` with a reason; `stdin`
defaults to empty (immediate EOF).

```yaml
tests:
  - id: sum
    input: "Read integers from stdin and print their sum."
    stdio:
      - {stdin: "1 2 3\n", expected_stdout: "6\n"}
      - {stdin: "", expected_stdout: "0\n"}
```

Related: `code_block_runs` only **parses** blocks (no execution); `code_test_passes` executes the
**first** python block with a config-level `test_code` (no per-case tests, `-c`, no temp dir, **no isolation**).

---

## `tool_call_match`

Deterministic pass/fail on the [tool-call log](#tool-call-log): compares the
calls the chat target returned with the case's expected calls. No judge
model. Scores `1.0` or `0.0`; a `0.0` reason names the first mismatch
(call numbers start at 1, in reply order).

### Expected calls

Per case, under `metadata.expected_calls`, in the possible_answer format of
the Berkeley Function Calling Leaderboard (BFCL): one mapping per expected
call, `function name -> {argument: [accepted values]}`.

```yaml
metadata:
  expected_calls:
    - get_weather:
        city: [Paris, paris]     # any one of these
        unit: [celsius, ""]      # "" among the values: argument may be omitted
```

- A bare mapping instead of a list is one call.
- An argument without `""` among its values is required.
- A value that is not a list is one accepted value. A list is always a set
  of alternatives, so a list-valued argument needs a list of lists
  (`ids: [[1, 2], [2, 1]]`).
- Arguments the call passes that are not listed fail it (`unexpected
  argument`).
- Tool names match exactly.

### Configuration Properties:
| Property | Type | Required | Description |
|---|---|---|---|
| `match` | `string` | No | Default `single`. See modes below. (`mode` is the pass/fail scoring mode shared by all evaluators.) |
| `case_sensitive` | `boolean` | No | Compare strings case-sensitively. Default `true`. |
| `normalize_whitespace` | `boolean` | No | Trim strings and collapse inner whitespace before comparing. Default `false`. |

| `match` | Expected calls | Passes when |
|---|---|---|
| `single` | exactly one | the log holds exactly one call and it matches; a second call fails as `extra call`. |
| `first` | exactly one | the first logged call matches; later calls are ignored. |
| `ordered` | one or more | the log has the same number of calls and call *i* matches expected call *i*. |
| `parallel` | one or more | the log has the same number of calls and they pair one-to-one with the expected calls in any order (alternatives are resolved by matching, not greedily). |
| `none` | none | the log is empty. Applies even when the case has no `expected_calls`; `expected_calls: []` is accepted. |

A mismatch in expected-call count for the mode (for example two calls under
`single`, or `[]` under `ordered`) scores `0.0` with a reason.

### Value comparison

Type-aware. Numbers compare by value (`1` = `1.0`); booleans are not
numbers; a string never equals a number (`"1"` != `1`); `null` equals
`null`. Lists compare element by element and objects key by key, with the
same rules (and the string options) applied inside. Strings are exact
unless `case_sensitive: false` and/or `normalize_whitespace: true`.

### Malformed arguments

A call with `raw_args` set (arguments were not a valid JSON object) never
matches any expected call, including one whose arguments are all optional;
the reason says the arguments were not valid JSON and shows the raw string.

### Applicability

Dataset-case evaluator. Outside `match: none`, a case without
`metadata.expected_calls` is not applicable: no result is recorded for it.
In contract mode (`eva run --contract`) and in the gateway there is no case
and no tool-call log, so the evaluator scores `0.0` with the reason
`needs a dataset case with metadata.expected_calls and the tool-call log of a chat-target run; not available here`.

```yaml
evaluators:
  - name: tool_call_match
    mode: binary
    match: parallel
tests:
  - id: two-cities
    input: Compare the weather in Paris and Rome.
    tools: [...]
    metadata:
      expected_calls:
        - get_weather: {city: [Paris]}
        - get_weather: {city: [Rome]}
```

`match` applies to the whole dataset: put cases that need another mode in
their own file. Sample: [`examples/tool-call-match.yaml`](examples/tool-call-match.yaml).

---

## `ifeval_check`

Runs the published IFEval and IFBench instruction verifiers on the reply, deterministically
and offline: no judge model. The verifiers are vendored from
[allenai/IFBench](https://github.com/allenai/IFBench) (Apache-2.0; it includes the
[google-research IFEval](https://github.com/google-research/google-research/tree/master/instruction_following_eval)
verifiers), pinned at commit `488918665d53`; see `core/third_party/ifbench/PROVENANCE.md`.
83 instruction ids are supported: the 25 IFEval ids (for example `length_constraints:number_words`,
`keywords:existence`, `detectable_format:json_format`, `language:response_language`) and the 58
IFBench ids (for example `count:numbers`, `format:no_whitespace`, `words:palindrome`).

**Dataset-case evaluator:** reads `metadata.instruction_id_list` and `metadata.kwargs` (a list
with one object per id, as in the google/IFEval and allenai/IFBench_test rows). A case without
`instruction_id_list` is not applicable: no result is recorded for it. `null` kwarg values are
dropped, as IFBench's rows carry every key with `null` for the unused ones. The case `input` is
passed to verifiers that need the prompt (for example `combination:repeat_prompt`).

Each instruction is checked **strict** (the reply as is) and **loose** (also tries the reply
without its first line, without its last line, without both, and each of those with `*`
removed; any variant passing counts). The case passes when **all** listed instructions pass
(prompt-level) at the `pass_on` level. The reason always lists strict and loose per
instruction, and the score metadata carries `strict`, `loose` and per-instruction results.
Reasoning (`<think>` or a separate field) is not graded.

An unknown instruction id, malformed metadata or a verifier error scores `0.0` with a reason
starting `error:` (metadata `error`); it never passes.

### Configuration Properties:
| Property | Type | Required | Description |
|---|---|---|---|
| `pass_on` | `string` | No | `strict` (default) or `loose`: which result decides pass or fail. |
| `instruction_id_list` | `list[string]` | No | Fallback ids when a case has none (contract mode). |
| `kwargs` | `list[object]` | No | Fallback kwargs, one per id. |

### Setup

Install the extra and fetch the nltk data once (the evaluator never downloads anything):

```sh
pip install "hop-top-eva[ifeval]"
eva data fetch            # see docs/cli-reference.md
```

Without the extra, or without the data, the case scores `0.0` and the reason names
`pip install "hop-top-eva[ifeval]"` or `eva data fetch`. Language detection (`langdetect`) is
seeded so grading is repeatable.

```yaml
evaluators:
  - name: ifeval_check
    pass_on: strict
tests:
  - id: ifeval-1
    input: "Write a short note. Use at least 20 words and include the keyword garden."
    metadata:
      instruction_id_list: ["length_constraints:number_words", "keywords:existence"]
      kwargs:
        - {relation: "at least", num_words: 20}
        - {keywords: ["garden"]}
```

---

## `latency`

*(Planned for Phase 1 Integration)*
Measures the response time and returns 1.0 if it falls within the allowed range.

---

## Tier 2 (LLM-as-Judge)

Requires `EVA_JUDGE_MODEL` in env. Full reference: [llm-evaluators.md](llm-evaluators.md).

**General:** `relevance`, `hallucination`, `tone`, `task_completion`, `safety`, `bias`,
`toxicity`, `summarization`, `prompt_alignment`, `goal_accuracy`, `geval`

**RAG:** `faithfulness`, `answer_relevancy`, `contextual_relevancy`, `contextual_precision`,
`contextual_recall`, `ragas`

**Tool-use / Agentic:** `tool_correctness`, `argument_correctness`, `tool_use`,
`step_efficiency`, `plan_adherence`, `plan_quality`

**Multi-turn:** `knowledge_retention`, `conversation_completeness`, `turn_relevancy`,
`turn_faithfulness`, `role_adherence`

**Image / Multimodal:** `text_to_image`, `image_editing`, `image_coherence`,
`image_helpfulness`, `image_reference`
