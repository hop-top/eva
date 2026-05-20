# core/evaluators/prose_assertion.py
"""Prose-assertion evaluator (T-0280..T-0286, feat-prose-assertion-eval).

Accepts a natural-language assertion string (e.g.
`"branch name does NOT contain 'worktree'"`) and either dispatches to an
existing programmatic evaluator (contains/regex/word_count/json_schema)
when the assertion shape matches a known rule, or falls back to
`llm_judge` when it doesn't.

Compiled assertions are cached by content hash so the same assertion text
produces the same evaluator plan deterministically across runs.

Key concepts:

- **rule table**: list of `(regex, factory)` pairs (RULE_TABLE below).
  Order matters — first match wins. Each entry's regex parses the
  assertion's *intent* (the verb-phrase shape) and produces a compiled
  `EvaluatorPlan`.
- **EvaluatorPlan**: lightweight, serialisable record of (evaluator name,
  config dict, optional `negate` flag). Stored in cache; instantiated to
  a real evaluator at run time.
- **ruleset_version**: integer constant. Bumped whenever the rule table
  changes. The cache key includes it so cache invalidation is automatic
  on rule changes. **This is the only invalidation knob — there is no
  TTL.** Document the bump policy in commit messages.
- **cache**: content-addressable, JSON-on-disk under
  `$XDG_STATE_HOME/eva/prose_assertion_cache/` (or
  `~/.local/state/eva/prose_assertion_cache/` if unset). Key is
  `sha256(assertion_text + "::" + ruleset_version)`.
- **llm_judge fallback**: invoked only when no rule matches. Model is
  pinned to `JUDGE_MODEL` + `JUDGE_TEMPERATURE` for reproducibility.

Usage:

    ev = ProseAssertionEvaluator(
        assertion="branch name does NOT contain 'worktree'",
        llm_adapter=optional_adapter,  # only used on cache-miss + no rule match
    )
    score = ev.run("feat/oauth-login")  # → Score(value=1.0)

Mood assertions ("uses imperative mood", "uses past tense") would ideally
dispatch to a dedicated MoodEvaluator (Agent A's P1 work on
feat-mood-eval). Until that lands in main, mood assertions fall through
to llm_judge. TODO: when MoodEvaluator lands, import it as
`from core.evaluators.mood import MoodEvaluator` and add a rule entry
that routes to it; bump `RULESET_VERSION`.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from core.evaluators.contains import ContainsEvaluator
from core.evaluators.json_schema_valid import JsonSchemaEvaluator
from core.evaluators.regex_match import RegexEvaluator
from core.evaluators.word_count import WordCountEvaluator
from core.models import Score


# ---------------------------------------------------------------------------
# Constants — bump policy lives here
# ---------------------------------------------------------------------------

#: Rule table version. **Bump on every rule table change** (add/remove/edit
#: entries, change capture groups, swap evaluator targets). Existing cache
#: entries become unreachable on bump; safe because cache is a pure
#: derivation of (assertion_text, ruleset_version).
RULESET_VERSION = 1

#: Pinned judge model — kept stable across releases for verdict
#: reproducibility. Change only with a corresponding RULESET_VERSION bump
#: (since cached plans encode the model id).
JUDGE_MODEL = "claude-haiku-4-5-20250101"

#: Pinned judge temperature. 0.0 = deterministic sampling. Lock to 0.0 so
#: the same prompt always yields the same first-line float.
JUDGE_TEMPERATURE = 0.0


# ---------------------------------------------------------------------------
# Compiled plan: serialisable, hashable, deterministic
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvaluatorPlan:
    """Serialised evaluator plan stored in the cache.

    `evaluator` is the registry name (`contains`, `regex`, `word_count`,
    `json_schema_valid`, or the special sentinel `llm_judge` for fallback).
    `config` is the kwargs dict passed to the factory. `negate` flips the
    final score (1.0 ↔ 0.0); used for "does NOT contain X" style rules
    where the underlying evaluator scores positive on match.
    """

    evaluator: str
    config: dict[str, Any]
    negate: bool = False

    def to_json(self) -> str:
        # `sort_keys=True` so structurally equal plans serialise byte-for-byte.
        return json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def from_json(cls, raw: str) -> EvaluatorPlan:
        d = json.loads(raw)
        return cls(evaluator=d["evaluator"], config=d["config"], negate=d.get("negate", False))


# ---------------------------------------------------------------------------
# Rule table
# ---------------------------------------------------------------------------
#
# Each entry: (regex, factory_callable).
#
# - regex: matches the assertion's surface shape. Use named groups so the
#   factory can pluck out the operand (substring, pattern, N, schema).
# - factory: takes the regex match object, returns an EvaluatorPlan.
#
# Coverage targets (cc-skills conventional-git corpus):
#   - "does NOT contain X" / "contains X"      → ContainsEvaluator
#   - "starts with X" / "ends with X"          → RegexEvaluator
#   - "is ≤ N chars" / "≤ N words" / "is N or fewer characters" → WordCountEvaluator
#     (length-by-words; chars routes to a char-length regex)
#   - "is valid JSON matching schema X"        → JsonSchemaEvaluator
#   - "matches pattern X" / "matches regex X"  → RegexEvaluator
#   - "uses imperative mood" / "uses past tense" → llm_judge fallback (TODO above)
#
# Order matters. More specific patterns must come BEFORE more general ones
# (e.g. "does NOT contain" must precede "contains").

# Quoted operand: matches 'x', "x", or `x` and captures the inner string.
_QUOTED = r"['\"`](?P<value>[^'\"`]+)['\"`]"

# Common assertion lead-in (optional): "response", "body", "subject",
# "text", "output", "branch name", "scope", "description", etc. We
# tolerate any noun-phrase prefix by allowing arbitrary words before the
# verb of interest.
_LEAD = r".*?\b"


def _negated_contains_factory(m: re.Match[str]) -> EvaluatorPlan:
    """`X does NOT contain Y` → ContainsEvaluator(substring=Y) with negate=True."""
    return EvaluatorPlan(
        evaluator="contains",
        config={"substring": m.group("value"), "case_sensitive": False},
        negate=True,
    )


def _contains_factory(m: re.Match[str]) -> EvaluatorPlan:
    return EvaluatorPlan(
        evaluator="contains",
        config={"substring": m.group("value"), "case_sensitive": False},
        negate=False,
    )


def _starts_with_factory(m: re.Match[str]) -> EvaluatorPlan:
    val = re.escape(m.group("value"))
    return EvaluatorPlan(
        evaluator="regex",
        config={"pattern": rf"^{val}"},
        negate=False,
    )


def _ends_with_factory(m: re.Match[str]) -> EvaluatorPlan:
    val = re.escape(m.group("value"))
    return EvaluatorPlan(
        evaluator="regex",
        config={"pattern": rf"{val}\s*$"},
        negate=False,
    )


def _max_words_factory(m: re.Match[str]) -> EvaluatorPlan:
    n = int(m.group("n"))
    return EvaluatorPlan(
        evaluator="word_count",
        config={"max": n},
        negate=False,
    )


def _max_chars_factory(m: re.Match[str]) -> EvaluatorPlan:
    n = int(m.group("n"))
    # `^.{0,N}$` with DOTALL ensures whole response ≤ N characters.
    # ContainsEvaluator can't express char-length, so we use a regex.
    return EvaluatorPlan(
        evaluator="regex",
        config={"pattern": rf"\A[\s\S]{{0,{n}}}\Z"},
        negate=False,
    )


def _matches_pattern_factory(m: re.Match[str]) -> EvaluatorPlan:
    return EvaluatorPlan(
        evaluator="regex",
        config={"pattern": m.group("value")},
        negate=False,
    )


# Rule table — first match wins. See module docstring for bump policy.
#
# Each tuple is (pattern_str, factory). `re.IGNORECASE` applied globally.
# Patterns use `_LEAD` to tolerate noun-phrase prefixes ("branch name X",
# "response X", "subject line X").
RULE_TABLE: list[tuple[str, Any]] = [
    # --- "does NOT contain X" ---------------------------------------------
    # Matches: "X does NOT contain 'y'", "X does not contain Y",
    # "does not include 'y'", "should not contain 'y'".
    # Negation lexicon: NOT|not|n't.
    (
        rf"{_LEAD}(?:does(?:\s+n[o']t)|do(?:es)?\s+not|should(?:\s+n[o']t)|should\s+not|must(?:\s+n[o']t)|must\s+not)\s+(?:contain|include)\s+(?:the\s+(?:word|phrase|string)\s+)?{_QUOTED}",
        _negated_contains_factory,
    ),
    # --- "contains X" -----------------------------------------------------
    # Plain positive containment. MUST come after the negated form above.
    (
        rf"{_LEAD}(?:contains|includes|has)\s+(?:the\s+(?:word|phrase|string)\s+)?{_QUOTED}",
        _contains_factory,
    ),
    # --- "starts with X" --------------------------------------------------
    (
        rf"{_LEAD}(?:starts?|begins?)\s+with\s+{_QUOTED}",
        _starts_with_factory,
    ),
    # --- "ends with X" ----------------------------------------------------
    (
        rf"{_LEAD}ends?\s+with\s+{_QUOTED}",
        _ends_with_factory,
    ),
    # --- "is ≤ N words" / "at most N words" / "N words or fewer" ----------
    (
        rf"{_LEAD}(?:is\s+)?(?:at\s+most|≤|<=|no\s+more\s+than)\s+(?P<n>\d+)\s+words?",
        _max_words_factory,
    ),
    (
        rf"{_LEAD}(?P<n>\d+)\s+words?\s+or\s+(?:fewer|less)",
        _max_words_factory,
    ),
    # --- "is ≤ N chars" / "at most N characters" / "N characters or fewer" -
    (
        rf"{_LEAD}(?:is\s+)?(?:at\s+most|≤|<=|no\s+more\s+than)\s+(?P<n>\d+)\s+(?:chars?|characters?)",
        _max_chars_factory,
    ),
    (
        rf"{_LEAD}(?P<n>\d+)\s+(?:chars?|characters?)\s+or\s+(?:fewer|less)",
        _max_chars_factory,
    ),
    (
        rf"{_LEAD}(?:is\s+)?(?P<n>\d+)\s+(?:chars?|characters?)\s+or\s+fewer",
        _max_chars_factory,
    ),
    # --- "matches pattern X" / "matches regex X" --------------------------
    (
        rf"{_LEAD}matches?\s+(?:the\s+)?(?:pattern|regex|regular\s+expression)\s+{_QUOTED}",
        _matches_pattern_factory,
    ),
]

#: Compiled rule table — same shape, regexes pre-compiled.
_COMPILED_RULES: list[tuple[re.Pattern[str], Any]] = [
    (re.compile(pat, re.IGNORECASE | re.DOTALL), factory)
    for pat, factory in RULE_TABLE
]


# ---------------------------------------------------------------------------
# Matcher
# ---------------------------------------------------------------------------


def match_assertion(assertion: str) -> EvaluatorPlan | None:
    """Return an `EvaluatorPlan` for `assertion`, or None on no match.

    `None` signals the caller should fall back to llm_judge.
    """
    for pattern, factory in _COMPILED_RULES:
        m = pattern.search(assertion)
        if m:
            return factory(m)
    return None


# ---------------------------------------------------------------------------
# Cache — content-addressable, on-disk JSON
# ---------------------------------------------------------------------------


def _cache_dir() -> Path:
    """Resolve cache directory honouring XDG_STATE_HOME."""
    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "state"
    return base / "eva" / "prose_assertion_cache"


#: Compile-time mode for the dispatcher.
#:
#:   - ``auto``: rule matcher first; llm_judge fallback (today's default).
#:   - ``judge_only``: skip the rule matcher, always route to llm_judge.
#:     Caller overrides the default when the rule's verdict is suspect
#:     (e.g. adversarial input, domain mismatch) or audit trace is required.
#:   - ``programmatic_only``: rule matcher only; raise at compile time if no
#:     rule matches. Caller asserts the assertion MUST be checkable
#:     deterministically. Fails at load, not at run.
Mode = str  # "auto" | "judge_only" | "programmatic_only"


def _cache_key(
    assertion: str,
    mode: Mode = "auto",
    ruleset_version: int = RULESET_VERSION,
) -> str:
    """Content hash of (assertion + ruleset_version + mode). Stable across runs.

    Including ``mode`` in the key means an assertion routed under ``auto`` does
    not collide with the same assertion routed under ``judge_only`` — each gets
    its own cache entry.
    """
    h = hashlib.sha256()
    h.update(assertion.encode("utf-8"))
    h.update(b"::")
    h.update(str(ruleset_version).encode("utf-8"))
    h.update(b"::")
    h.update(mode.encode("utf-8"))
    return h.hexdigest()


def cache_load(
    assertion: str,
    mode: Mode = "auto",
    ruleset_version: int = RULESET_VERSION,
) -> EvaluatorPlan | None:
    """Return cached plan for `(assertion, mode)`, or None on miss / read error.

    Read errors are silent — the caller treats them as a miss and re-compiles.
    """
    path = _cache_dir() / _cache_key(assertion, mode, ruleset_version)
    if not path.exists():
        return None
    try:
        return EvaluatorPlan.from_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError):
        return None


def cache_store(
    assertion: str,
    plan: EvaluatorPlan,
    mode: Mode = "auto",
    ruleset_version: int = RULESET_VERSION,
) -> None:
    """Write `plan` to the cache. Silent on write error (best-effort)."""
    cache_dir = _cache_dir()
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        path = cache_dir / _cache_key(assertion, mode, ruleset_version)
        path.write_text(plan.to_json(), encoding="utf-8")
    except OSError:
        pass  # cache miss → re-compile; not fatal


# ---------------------------------------------------------------------------
# Plan → evaluator instantiation
# ---------------------------------------------------------------------------


def _instantiate(plan: EvaluatorPlan, llm_adapter: Any | None = None) -> Any:
    """Build a runnable evaluator from a plan.

    The special `llm_judge` plan needs an LLM adapter. Programmatic plans
    don't — they're constructed directly.
    """
    if plan.evaluator == "contains":
        return ContainsEvaluator(**plan.config)
    if plan.evaluator == "regex":
        return RegexEvaluator(**plan.config)
    if plan.evaluator == "word_count":
        return WordCountEvaluator(**plan.config)
    if plan.evaluator == "json_schema_valid":
        return JsonSchemaEvaluator(**plan.config)
    if plan.evaluator == "llm_judge":
        if llm_adapter is None:
            raise ValueError(
                "llm_judge plan requires an llm_adapter; none provided. "
                "Pass llm_adapter= when constructing ProseAssertionEvaluator."
            )
        return _LLMJudgePlanEvaluator(
            assertion=plan.config["assertion"],
            llm_adapter=llm_adapter,
        )
    raise ValueError(f"unknown evaluator name in plan: {plan.evaluator}")


# ---------------------------------------------------------------------------
# llm_judge fallback — synchronous wrapper for the dispatcher
# ---------------------------------------------------------------------------


class _LLMJudgePlanEvaluator:
    """Single-shot llm_judge over a free-form prose assertion.

    Used only when the rule matcher returns None. Pins model + temperature
    (constants above) so verdicts are reproducible across runs of the same
    cached plan.

    Exposes a synchronous `run(response)` for parity with programmatic
    evaluators (the dispatcher is sync). Internally calls asyncio to drive
    the async LiteLLMAdapter.complete().
    """

    def __init__(self, assertion: str, llm_adapter: Any):
        self.assertion = assertion
        self.llm = llm_adapter

    def run(self, response: str) -> Score:
        import asyncio

        judge_prompt = (
            "You are an evaluator. Given a response and a single assertion, "
            "decide whether the response satisfies the assertion.\n\n"
            f"Assertion: {self.assertion}\n"
            f"Response: {response}\n\n"
            "Reply with a single float on the first line: 1.0 if the assertion "
            "holds, 0.0 if it does not. On the next line, give a one-sentence "
            "reason."
        )
        # Run the async LLM call from a sync context. If we're already in an
        # event loop, the caller should use the async path directly — but
        # the public `run()` API is sync for parity with other evaluators.
        coro = self.llm.complete(
            [{"role": "user", "content": judge_prompt}],
            temperature=JUDGE_TEMPERATURE,
        )
        try:
            completion = asyncio.run(coro)
        except RuntimeError:
            # Already in an event loop (e.g. nested in pytest-asyncio). Fall
            # back to creating a new loop in a thread. Rare path.
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                completion = pool.submit(asyncio.run, self.llm.complete(
                    [{"role": "user", "content": judge_prompt}],
                    temperature=JUDGE_TEMPERATURE,
                )).result()

        from core.evaluators.llm_judge import parse_score

        value, reason = parse_score(completion.content)
        return Score(
            value=value,
            reason=reason,
            metadata={
                "evaluator_id": "prose_assertion_llm_judge",
                "judge_model": JUDGE_MODEL,
                "judge_temperature": JUDGE_TEMPERATURE,
            },
        )


# ---------------------------------------------------------------------------
# Public evaluator class
# ---------------------------------------------------------------------------


class ProseAssertionEvaluator:
    """Dispatching evaluator for natural-language assertions.

    Compile flow (constructor):
      1. cache lookup on `(assertion, mode)`
      2. on miss, branch on mode:
         - ``auto``: rule matcher → plan; llm_judge fallback on no match
         - ``judge_only``: skip matcher, build an llm_judge plan
         - ``programmatic_only``: rule matcher → plan; raise if no match
      3. on miss: write the chosen plan to cache

    Run flow (`.run(response)`):
      Instantiates the cached plan's evaluator and delegates to its
      `.run(response)`. Negation (if `plan.negate=True`) flips the result.

    Modes (see ``Mode`` above):

      - ``auto`` (default): same as v1 behaviour. Programmatic where
        possible, llm_judge otherwise.
      - ``judge_only``: caller wants the judge regardless. Use when the
        rule's verdict is suspect (adversarial input, domain mismatch) or
        an audit trace is required.
      - ``programmatic_only``: caller asserts deterministic checkability.
        ``ValueError`` is raised at construction time if no rule matches,
        so contract authors hear about ambiguous assertions at load, not
        at run.
    """

    def __init__(
        self,
        assertion: str,
        llm_adapter: Any | None = None,
        mode: Mode = "auto",
    ):
        if mode not in ("auto", "judge_only", "programmatic_only"):
            raise ValueError(
                f"unknown prose-assertion mode: {mode!r}; "
                "expected 'auto', 'judge_only', or 'programmatic_only'"
            )
        self.assertion = assertion
        self.llm_adapter = llm_adapter
        self.mode = mode
        self.plan = self._compile(assertion, mode)

    @staticmethod
    def _compile(assertion: str, mode: Mode = "auto") -> EvaluatorPlan:
        cached = cache_load(assertion, mode)
        if cached is not None:
            return cached

        if mode == "judge_only":
            plan: EvaluatorPlan | None = EvaluatorPlan(
                evaluator="llm_judge",
                config={"assertion": assertion},
                negate=False,
            )
        else:
            plan = match_assertion(assertion)
            if plan is None:
                if mode == "programmatic_only":
                    raise ValueError(
                        f"prose-assertion mode=programmatic_only: no rule "
                        f"matches assertion {assertion!r}. Either rephrase to "
                        "match a known rule, add a rule, or change mode to "
                        "'auto' / 'judge_only'."
                    )
                # mode == "auto" — fall back to llm_judge
                plan = EvaluatorPlan(
                    evaluator="llm_judge",
                    config={"assertion": assertion},
                    negate=False,
                )

        cache_store(assertion, plan, mode)
        return plan

    def run(self, response: str) -> Score:
        evaluator = _instantiate(self.plan, llm_adapter=self.llm_adapter)
        score = evaluator.run(response)
        if self.plan.negate:
            # Flip pass/fail. Preserve reason but rewrite the framing so the
            # caller sees why a negation failed (i.e. forbidden substring
            # WAS present).
            if score.value == 1.0:
                return Score(
                    value=0.0,
                    reason=f"assertion violated (negated): {self.assertion}",
                    metadata=score.metadata,
                )
            return Score(value=1.0, reason=None, metadata=score.metadata)
        return score

    _run = run  # backward-compat alias
