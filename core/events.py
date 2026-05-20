# core/events.py
"""Lightweight event sink API for agent wrappers and plugins.

Usage:
    sink = EventSink()
    context["event_sink"] = sink
    ...
    sink.emit_tool_call("my_tool", {"arg": 1}, result="ok", duration_ms=42)
    persisted = sink.events  # list[ToolCallEvent]

Default (no-op) sink — callers never need to guard:
    context.setdefault("event_sink", NullEventSink())
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ToolCallEvent:
    """Immutable record of a single tool invocation."""

    tool_name: str
    args: dict[str, Any]
    result: Any | None = None
    error: str | None = None
    duration_ms: int | None = None
    trace_id: str | None = None
    span_id: str | None = None
    step_index: int | None = None
    started_at: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


class EventSink:
    """Collects ToolCallEvents in memory during a run.

    Intended lifetime: one run / one gateway request.
    After the run completes the caller drains `.events` and persists them.
    """

    def __init__(self) -> None:
        self.events: list[ToolCallEvent] = []

    def emit_tool_call(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        result: Any | None = None,
        error: str | None = None,
        duration_ms: int | None = None,
        trace_id: str | None = None,
        span_id: str | None = None,
        step_index: int | None = None,
        started_at: datetime | None = None,
    ) -> ToolCallEvent:
        """Record a tool call and return the stored event."""
        evt = ToolCallEvent(
            tool_name=tool_name,
            args=args,
            result=result,
            error=error,
            duration_ms=duration_ms,
            trace_id=trace_id,
            span_id=span_id,
            step_index=step_index,
            started_at=started_at or datetime.now(tz=timezone.utc),
        )
        self.events.append(evt)
        return evt

    def drain(self) -> list[ToolCallEvent]:
        """Return all events and clear the internal buffer."""
        evts, self.events = self.events, []
        return evts


class NullEventSink:
    """Silent no-op sink — safe default; callers need no guard checks."""

    @property
    def events(self) -> list[ToolCallEvent]:
        """Return a fresh empty list each access — Null sink has no state.

        Previously this was a class-level mutable attribute. If any caller
        mutated sink.events (e.g. sink.events.append(...)) the mutation
        would persist across every NullEventSink() instance for the lifetime
        of the process. A property returning a new list makes the no-op
        semantics structural: there is genuinely nothing to share.
        """
        return []

    def emit_tool_call(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        result: Any | None = None,
        error: str | None = None,
        duration_ms: int | None = None,
        trace_id: str | None = None,
        span_id: str | None = None,
        step_index: int | None = None,
        started_at: datetime | None = None,
    ) -> None:
        """Discard event silently."""

    def drain(self) -> list[ToolCallEvent]:
        return []
