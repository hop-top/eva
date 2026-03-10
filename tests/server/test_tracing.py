# tests/server/test_tracing.py
import pytest
from server.gateway.tracing import get_tracer, start_span, SpanContext


def test_get_tracer_returns_tracer():
    tracer = get_tracer()
    assert tracer is not None


def test_start_span_returns_context_manager():
    tracer = get_tracer()
    ctx = start_span(tracer, "test.operation", {"key": "value"})
    assert ctx is not None


def test_span_context_has_trace_id():
    tracer = get_tracer()
    with start_span(tracer, "test.op", {}) as span_ctx:
        assert isinstance(span_ctx, SpanContext)
        # trace_id is a hex string or None when using NoopTracer
        assert span_ctx.trace_id is None or isinstance(span_ctx.trace_id, str)
