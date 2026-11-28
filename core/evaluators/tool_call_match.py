# core/evaluators/tool_call_match.py
"""ToolCallMatchEvaluator — deterministic check of the tool-call log.

Compares the calls a chat target returned (``tool_events`` in the evaluation
context, see core.events.ToolCallEvent) with the case's expected calls
(``metadata.expected_calls``), in the possible_answer format of the Berkeley
Function Calling Leaderboard (BFCL)::

    [{"get_weather": {"city": ["Paris", "paris"], "unit": ["celsius", ""]}}]

One mapping per expected call: function name -> {argument: [accepted
values]}. An empty string among the accepted values means the argument may
be omitted. No judge model: the score is 1.0 or 0.0 with the first mismatch
as the reason.
"""
from __future__ import annotations

from typing import Any

from core.events import ToolCallEvent
from core.models import Score

MODES = ("single", "parallel", "ordered", "none", "first")

_NAME = "tool_call_match"
_NO_CASE = (
    f"{_NAME}: needs a dataset case with metadata.expected_calls and the "
    "tool-call log of a chat-target run; not available here"
)


def _short(value: Any, limit: int = 80) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


class ToolCallMatchEvaluator:
    """Parameters

    match:
        ``single`` (default) exactly one call expected and logged;
        ``parallel`` several calls, any order; ``ordered`` several calls in
        order; ``none`` no call expected; ``first`` only the first logged
        call is checked, later calls are ignored.
    case_sensitive:
        Compare strings case-sensitively (default ``True``).
    normalize_whitespace:
        Trim strings and collapse inner whitespace runs before comparing
        (default ``False``).
    """

    evaluator_id = _NAME

    def __init__(
        self,
        match: str = "single",
        case_sensitive: bool = True,
        normalize_whitespace: bool = False,
    ):
        self.match = match
        self.case_sensitive = case_sensitive
        self.normalize_whitespace = normalize_whitespace

    # -- entry points ------------------------------------------------------

    def run(self, response: str) -> Score:
        """Contract mode / gateway: no case and no tool-call log reach here."""
        return Score(value=0.0, reason=_NO_CASE)

    async def evaluate(self, prompt: str, response: str, **context: Any) -> Score | None:
        """Score one case; ``None`` = not applicable (no expected calls)."""
        meta = context.get("metadata") or {}
        if "expected_calls" in meta:
            expected = meta["expected_calls"]
        elif self.match == "none":
            expected = []
        else:
            return None
        return self.check(context.get("tool_events") or [], expected)

    # -- scoring -----------------------------------------------------------

    def check(self, events: list[ToolCallEvent], expected: Any) -> Score:
        reason = self._mismatch(list(events), expected)
        if reason is None:
            return Score(value=1.0)
        return Score(value=0.0, reason=f"{_NAME}: {reason}")

    def _mismatch(self, events: list[ToolCallEvent], expected: Any) -> str | None:
        if self.match not in MODES:
            return f"unknown match {self.match!r}; use one of {', '.join(MODES)}"
        specs, err = _parse_expected(expected)
        if err:
            return err

        if self.match == "none":
            if specs:
                return "match: none expects no call, but expected_calls lists some"
            if events:
                return f"expected no tool call, got {len(events)}: {_names(events)}"
            return None

        if not specs:
            return "expected_calls is empty; use match: none when no call is expected"

        if self.match in ("single", "first"):
            if len(specs) != 1:
                return (
                    f"match: {self.match} needs exactly one expected call, "
                    f"expected_calls has {len(specs)}"
                )
            if not events:
                return f"expected a call to {specs[0][0]!r}, no tool call logged"
            err = self._call_mismatch(events[0], specs[0])
            if err:
                return f"call 1: {err}"
            if self.match == "single" and len(events) > 1:
                return f"extra call 2 ({events[1].tool_name}) after the expected call"
            return None

        if self.match == "ordered":
            for i, (call, spec) in enumerate(zip(events, specs)):
                err = self._call_mismatch(call, spec)
                if err:
                    return f"call {i + 1}: {err}"
            if len(events) < len(specs):
                return (
                    f"missing call {len(events) + 1}: expected "
                    f"{_describe(specs[len(events)])}"
                )
            if len(events) > len(specs):
                return (
                    f"extra call {len(specs) + 1} "
                    f"({events[len(specs)].tool_name}) after the expected calls"
                )
            return None

        return self._parallel_mismatch(events, specs)

    def _parallel_mismatch(self, events, specs) -> str | None:
        compat = [
            [self._call_mismatch(call, spec) is None for call in events]
            for spec in specs
        ]
        owner: dict[int, int] = {}  # event index -> spec index

        def assign(i: int, seen: set[int]) -> bool:
            for j, ok in enumerate(compat[i]):
                if ok and j not in seen:
                    seen.add(j)
                    if j not in owner or assign(owner[j], seen):
                        owner[j] = i
                        return True
            return False

        unmatched = [i for i in range(len(specs)) if not assign(i, set())]
        if unmatched:
            i = unmatched[0]
            name = specs[i][0]
            same = [j for j, c in enumerate(events) if c.tool_name == name]
            if not same:
                return (
                    f"expected a call to {name!r}, not in the log "
                    f"(logged: {_names(events) or 'no call'})"
                )
            # Prefer a same-name call no other expected call claimed.
            for j in sorted(same, key=lambda j: j in owner):
                if not compat[i][j]:
                    return f"call {j + 1}: {self._call_mismatch(events[j], specs[i])}"
            return (
                f"expected call {i + 1} to {name!r}: no unpaired logged call left"
            )
        extra = [j for j in range(len(events)) if j not in owner]
        if extra:
            j = extra[0]
            return f"extra call {j + 1} ({events[j].tool_name}) not among the expected calls"
        return None

    def _call_mismatch(self, call: ToolCallEvent, spec) -> str | None:
        name, accepted = spec
        if call.tool_name != name:
            return f"called {call.tool_name!r}, expected {name!r}"
        label = f"{name}"
        if call.raw_args is not None:
            return (
                f"{label}: arguments were not valid JSON "
                f"(got {_short(call.raw_args)})"
            )
        args = call.args or {}
        for arg, vals in accepted.items():
            if arg not in args:
                if "" in vals:
                    continue
                return f"{label}: missing required argument {arg!r}"
            got = args[arg]
            if not any(self._equal(got, want) for want in vals):
                return (
                    f"{label}: argument {arg!r} is {_short(got)}, "
                    f"expected one of {_short(vals, 120)}"
                )
        for arg in args:
            if arg not in accepted:
                return f"{label}: unexpected argument {arg!r}"
        return None

    # -- value comparison --------------------------------------------------

    def _equal(self, got: Any, want: Any) -> bool:
        if isinstance(got, str) or isinstance(want, str):
            if not (isinstance(got, str) and isinstance(want, str)):
                return False
            return self._norm(got) == self._norm(want)
        if isinstance(got, bool) or isinstance(want, bool):
            return isinstance(got, bool) and isinstance(want, bool) and got == want
        if _is_number(got) or _is_number(want):
            return _is_number(got) and _is_number(want) and got == want
        if isinstance(got, (list, tuple)) and isinstance(want, (list, tuple)):
            return len(got) == len(want) and all(
                self._equal(g, w) for g, w in zip(got, want)
            )
        if isinstance(got, dict) and isinstance(want, dict):
            return got.keys() == want.keys() and all(
                self._equal(got[k], want[k]) for k in got
            )
        return got is None and want is None

    def _norm(self, s: str) -> str:
        if self.normalize_whitespace:
            s = " ".join(s.split())
        if not self.case_sensitive:
            s = s.casefold()
        return s


def _describe(spec) -> str:
    name, accepted = spec
    args = ", ".join(f"{a}={_short(v, 40)}" for a, v in accepted.items())
    return f"{name}({args})"


def _names(events: list[ToolCallEvent]) -> str:
    return ", ".join(e.tool_name for e in events)


def _parse_expected(expected: Any):
    """-> ([(name, {arg: [accepted...]})], error). A bare mapping is one call."""
    bad = "invalid expected_calls: "
    if isinstance(expected, dict):
        expected = [expected]
    if not isinstance(expected, list):
        return None, bad + "must be a list of {function: {argument: [values]}}"
    specs = []
    for i, item in enumerate(expected, 1):
        if not isinstance(item, dict) or len(item) != 1:
            return None, bad + f"entry {i} must map one function name to its arguments"
        (name, args), = item.items()
        if args is None:
            args = {}
        if not isinstance(args, dict):
            return None, bad + f"entry {i} ({name}): arguments must be a mapping"
        accepted = {
            arg: list(vals) if isinstance(vals, list) else [vals]
            for arg, vals in args.items()
        }
        specs.append((name, accepted))
    return specs, None
