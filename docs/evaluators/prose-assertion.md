# prose-assertion evaluator

A single dispatching evaluator that accepts a **natural-language
assertion** and routes it to a programmatic evaluator
(contains/regex/word_count/json_schema) when the assertion shape
matches a known rule, or falls back to `llm_judge` when it doesn't.

Compiled assertions are cached by content hash, so the same assertion
text deterministically produces the same evaluator plan across runs.

---

## When to use

Pick `prose_assertion` when:

- You have an existing **cc-skills-style assertion corpus** (each
  assertion already phrased in natural language as part of a skill
  eval suite) and want eva to evaluate them without first translating
  each into a hand-coded evaluator.
- You're writing a contract pack and want **prose for judgement-style
  checks and verbs for programmatic checks in the same file**.
- You're scoring a skill from `hop-top/ben`'s
  [`feat-skill-eval-suite`](../../../ben/.tlc/tracks/feat-skill-eval-suite)
  adapter — that adapter invokes this evaluator per-assertion.

Pick a hand-authored evaluator (`contains`, `regex`, `word_count`,
`json_schema_valid`, `last_paragraph_regex`, `no_pii`) when:

- The assertion is **so common in your codebase that the verb form is
  clearer than the prose form** (e.g. `word_count` with `max: 700` is
  more obvious than `"is at most 700 words"`).
- You want **factory-level guarantees** — `word_count` validates its
  config at construction time; a prose assertion compiles lazily.
- You're authoring a v1.0 contract where rule-version drift is a
  liability.

---

## Rule coverage

The matcher's rule table covers six families of assertion shapes drawn
from the cc-skills `conventional-git` corpus. Order matters — more
specific patterns precede more general ones (e.g. "does NOT contain"
must match before "contains").

| Assertion shape                                          | Routes to              | Notes                                  |
|----------------------------------------------------------|------------------------|----------------------------------------|
| `"X does NOT contain 'Y'"`                               | `ContainsEvaluator`    | `negate=True`; case-insensitive        |
| `"X contains 'Y'"`                                       | `ContainsEvaluator`    | case-insensitive                       |
| `"X starts with 'Y'"`                                    | `RegexEvaluator`       | anchored at start                      |
| `"X ends with 'Y'"`                                      | `RegexEvaluator`       | anchored at end (trailing whitespace ok) |
| `"is at most N words"` / `"≤ N words"` / `"N words or fewer"` | `WordCountEvaluator`   | sets `max`                             |
| `"is at most N chars"` / `"N characters or fewer"`       | `RegexEvaluator`       | `\A.{0,N}\Z` (whole-response)          |
| `"matches pattern 'X'"` / `"matches regex 'X'"`          | `RegexEvaluator`       | passes operand straight through        |
| `"is valid JSON matching schema X"`                      | `JsonSchemaEvaluator`  | reserved for future rule expansion     |
| `"uses imperative mood"` / `"uses past tense"`           | **llm_judge fallback** | until `MoodEvaluator` lands (Agent A)  |

The `_QUOTED` operand pattern accepts single quotes, double quotes, or
backticks. Lead-in is permissive: any noun-phrase prefix works
(`"branch name"`, `"response"`, `"subject line"`, `"description"`,
etc.).

### Coverage benchmark

On the cc-skills `conventional-git` evals corpus (21 representative
assertions), the rule table currently routes **86%** of assertions to
a programmatic evaluator (18/21). The acceptance criterion is ≥80%.
Unmatched items are mood ("uses imperative mood", "uses past tense") —
they fall through to `llm_judge` until `MoodEvaluator` (Agent A's
`feat-mood-eval` track) lands.

See `tests/unit/test_prose_assertion.py::CC_SKILLS_CORPUS` for the
benchmark dataset.

---

## llm_judge fallback

When `match_assertion()` returns `None`, the dispatcher synthesises an
`EvaluatorPlan(evaluator="llm_judge", config={"assertion": "..."})` and
caches it. Subsequent runs hit the cache and instantiate
`_LLMJudgePlanEvaluator`.

### Pinned model + temperature

For **reproducible verdicts across runs of the same compile**, the
judge is pinned:

| Knob          | Value                          | Why                                          |
|---------------|--------------------------------|----------------------------------------------|
| Model         | `claude-haiku-4-5-20250101`    | Small, fast, cheap; stable for ≥1y           |
| Temperature   | `0.0`                          | Deterministic sampling                       |

Both are constants in `core/evaluators/prose_assertion.py`. **Changing
either requires a `RULESET_VERSION` bump** (existing cached plans
would otherwise resolve to the old model).

### Single-shot, single-judge

No multi-turn judging, no judge consensus. One LLM call per evaluation.
Failure modes are documented in the parent
[llm-evaluators.md](../llm-evaluators.md): network errors propagate;
parse failures fall back to score 0.5 (see `parse_score`).

---

## Cache behavior

The compiled plan is stored on disk under
`$XDG_STATE_HOME/eva/prose_assertion_cache/`
(default `~/.local/state/eva/prose_assertion_cache/`).

| Property        | Detail                                                                              |
|-----------------|-------------------------------------------------------------------------------------|
| Key             | `sha256(assertion_text + "::" + RULESET_VERSION)`                                   |
| Value           | JSON-serialised `EvaluatorPlan` (`{evaluator, config, negate}`)                     |
| Determinism     | `json.dumps(..., sort_keys=True)` — two equal plans serialise to identical bytes    |
| Hit semantics   | Skip rule match + LLM judge entirely; just instantiate the plan                     |
| Miss semantics  | Run matcher → maybe llm_judge plan → write cache → instantiate                      |
| Invalidation    | Bump `RULESET_VERSION` (in code). **No TTL.**                                       |
| Read errors     | Treated as miss (silent fall-through to re-compile)                                 |
| Write errors    | Best-effort; silent (next run re-compiles)                                          |

### When to bump `RULESET_VERSION`

Bump the constant in `core/evaluators/prose_assertion.py` whenever:

- A rule entry is added, removed, or its regex is edited.
- A factory's `EvaluatorPlan` output shape changes (different
  evaluator name or different config keys).
- The pinned judge model or temperature changes.
- The cache key derivation itself changes.

The bump invalidates all on-disk cache entries by changing the hash
inputs. Old files become unreachable; users can `rm -rf
$XDG_STATE_HOME/eva/prose_assertion_cache` to reclaim disk if needed.

---

## Contract pack syntax

A YAML contract may declare top-level `assertions:` alongside (or
instead of) `evaluators:`. Each assertion compiles into one
`EvaluatorRef` of `name: prose_assertion`.

```yaml
# contracts/cc-skills-branch-naming.yaml
name: cc-skills-branch-naming
provider: branch-namer
assertions:
  - "branch name does NOT contain 'worktree'"
  - "branch name starts with 'feat/'"
  - "branch name is at most 50 chars"
```

Mixing programmatic evaluators and assertions in the same file is
supported:

```yaml
name: mixed
provider: writer
evaluators:
  - name: word_count
    mode: binary
    max: 100
assertions:
  - "response contains 'refund'"
  - "response does NOT contain 'apology'"
```

Both `evaluators:` and `assertions:` are accepted; the loader
translates `assertions:` into prose_assertion entries and appends
them. Each becomes a separate check in the
[ContractRunReport](../cli-reference.md).

### Per-assertion mode override (T-0380)

The default routing — programmatic-first with `llm_judge` fallback —
is right most of the time. Three cases warrant an override:

- **The rule is wrong.** A programmatic verdict that's
  deterministically wrong is worse than a noisy judge that's right.
- **Adversarial input.** A model that pads with imperative verbs
  while the actual intent is past-tense can fool a POS-tag mood
  check; the judge catches the intent.
- **Audit requirement.** Some authors want the judge's reasoning
  trace attached to the verdict for compliance.

Switch to dict-shaped entries to opt into either of two overrides:

```yaml
assertions:
  # Default routing — bare string, mode='auto'
  - "branch name does NOT contain 'worktree'"

  # Force the judge even when a rule matches
  - text: "uses imperative mood"
    judge: true

  # Refuse the judge — fail at load if no rule matches
  - text: "branch name starts with 'feat/'"
    programmatic_only: true
```

Modes:

- `auto` (default): rule matcher → programmatic plan; `llm_judge`
  fallback when no rule matches.
- `judge_only` (set via `judge: true`): skip the matcher; always
  build an `llm_judge` plan. Caller wants the judge regardless.
- `programmatic_only` (set via `programmatic_only: true`): rule
  matcher only; raise `ValueError` at construction time if no rule
  matches. Caller asserts deterministic checkability — contract
  authors hear about ambiguous assertions at load, not at run.

Setting both `judge: true` and `programmatic_only: true` on the
same entry is a contract error (they're contradictory).

The cache key includes the mode, so an assertion routed under
`auto` does not collide with the same assertion routed under
`judge_only` — each gets its own cache entry.

### Validation

- `assertions:` must be a **list**. Non-list → loader raises
  `ContractValidationError("must be a list")`.
- Each entry must be a **string or dict**. Other types → loader
  raises `ContractValidationError("must be a string or dict")`.
- A dict entry must have a non-empty `text:` field. Missing/empty
  → `ContractValidationError("must have a non-empty text: field")`.
- A dict entry cannot set both `judge: true` and
  `programmatic_only: true` → `ContractValidationError("cannot set
  both")`.

---

## Cross-references

- **Skill-eval consumer**: `hop-top/ben`'s
  `feat-skill-eval-suite` track — its `adapter: eva` invokes
  `prose_assertion` per assertion in a skill's `evals.json`.
- **Existing evaluators**: see
  [evaluators-reference.md](../evaluators-reference.md).
- **Llm_judge family**: see
  [llm-evaluators.md](../llm-evaluators.md).
- **Source**: `core/evaluators/prose_assertion.py`.
- **Tests**: `tests/unit/test_prose_assertion.py`,
  `tests/e2e/test_prose_assertion_evaluator.py`.
- **Track plan**: `.tlc/tracks/feat-prose-assertion-eval/plan.md`.
