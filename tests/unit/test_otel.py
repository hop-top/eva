# tests/unit/test_otel.py
"""Tests for NoopOtelAdapter and StdoutOtelAdapter."""
import json
import pytest
from core.otel import NoopOtelAdapter, NoopSpan, StdoutOtelAdapter, StdoutSpan
from core.adapters import Span


def test_noop_adapter_returns_noop_span():
    adapter = NoopOtelAdapter()
    span = adapter.start_span("op.call")
    assert isinstance(span, NoopSpan)
    assert span.name == "op.call"


def test_noop_span_end_is_silent():
    adapter = NoopOtelAdapter()
    span = adapter.start_span("x", attributes={"a": 1})
    span.end()  # must not raise or print


def test_noop_span_attributes_passed():
    adapter = NoopOtelAdapter()
    span = adapter.start_span("x", attributes={"model": "gpt-4"})
    assert span.attributes["model"] == "gpt-4"


def test_noop_span_default_attributes():
    adapter = NoopOtelAdapter()
    span = adapter.start_span("x")
    assert span.attributes == {}


def test_stdout_adapter_returns_stdout_span():
    adapter = StdoutOtelAdapter()
    span = adapter.start_span("emit")
    assert isinstance(span, StdoutSpan)


def test_stdout_span_end_prints_json(capsys):
    adapter = StdoutOtelAdapter()
    span = adapter.start_span("my.span", attributes={"key": "val"})
    span.end()
    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["span"] == "my.span"
    assert data["attributes"]["key"] == "val"


def test_otel_noop_fixture(otel_noop):
    span = otel_noop.start_span("fixture.test")
    assert isinstance(span, Span)
    span.end()
