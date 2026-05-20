# tests/unit/test_events.py
"""Tests for core/events.py — EventSink + NullEventSink semantics."""
from __future__ import annotations

from core.events import EventSink, NullEventSink, ToolCallEvent


# ---------------------------------------------------------------------------
# NullEventSink — per-instance isolation regression
# ---------------------------------------------------------------------------


def test_null_event_sink_events_returns_empty_list():
    """Default no-op sink reports no events."""
    sink = NullEventSink()
    assert sink.events == []


def test_null_event_sink_emit_does_not_record():
    """emit_tool_call is a no-op on NullEventSink — events stays empty."""
    sink = NullEventSink()
    sink.emit_tool_call("ignored", {"x": 1}, result="r")
    assert sink.events == []


def test_null_event_sink_drain_returns_empty():
    """drain() on a NullEventSink always yields an empty list."""
    sink = NullEventSink()
    assert sink.drain() == []


def test_two_null_event_sinks_do_not_share_state():
    """Regression: a previous revision stored events as a class-level
    mutable list. Any caller that appended to one instance's .events would
    poison every other NullEventSink for the rest of the process. The
    property-returning-fresh-list shape makes that impossible.
    """
    sink_a = NullEventSink()
    sink_b = NullEventSink()

    # Attempt to mutate one instance's events list — even if it succeeds in
    # appending to the returned local, it must NOT leak into the other
    # instance's view because the property always returns a fresh list.
    leak_attempt = sink_a.events
    leak_attempt.append(
        ToolCallEvent(tool_name="leak", args={"owner": "sink_a"})
    )

    # Both sinks still report empty — no shared state.
    assert sink_a.events == []
    assert sink_b.events == []


def test_null_event_sink_property_returns_independent_lists():
    """Each access to .events yields a fresh list — never the same object."""
    sink = NullEventSink()
    list_one = sink.events
    list_two = sink.events
    assert list_one is not list_two


# ---------------------------------------------------------------------------
# EventSink — happy path
# ---------------------------------------------------------------------------


def test_event_sink_records_emitted_call():
    sink = EventSink()
    sink.emit_tool_call("search", {"q": "x"}, result="hit", duration_ms=12)
    assert len(sink.events) == 1
    evt = sink.events[0]
    assert evt.tool_name == "search"
    assert evt.args == {"q": "x"}
    assert evt.result == "hit"
    assert evt.duration_ms == 12


def test_event_sink_drain_clears_buffer():
    sink = EventSink()
    sink.emit_tool_call("t1", {})
    sink.emit_tool_call("t2", {})
    drained = sink.drain()
    assert len(drained) == 2
    assert sink.events == []


def test_event_sink_instances_are_isolated():
    """Two EventSink instances must have independent buffers."""
    sink_a = EventSink()
    sink_b = EventSink()
    sink_a.emit_tool_call("a_only", {})
    assert len(sink_a.events) == 1
    assert sink_b.events == []
