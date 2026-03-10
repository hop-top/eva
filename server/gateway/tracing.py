# server/gateway/tracing.py — OTEL span helpers with noop fallback
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Generator

try:
    from opentelemetry import trace
    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False


@dataclass
class SpanContext:
    trace_id: str | None
    span_id: str | None


class _NoopTracer:
    """Fallback when opentelemetry is not installed."""

    @contextmanager
    def _noop_span(self, name: str, attributes: dict) -> Generator[SpanContext, None, None]:
        yield SpanContext(trace_id=None, span_id=None)


def get_tracer(name: str = "eva.server"):
    if _OTEL_AVAILABLE:
        return trace.get_tracer(name)
    return _NoopTracer()


@contextmanager
def start_span(tracer, operation: str, attributes: dict) -> Generator[SpanContext, None, None]:
    if isinstance(tracer, _NoopTracer):
        with tracer._noop_span(operation, attributes) as ctx:
            yield ctx
        return

    with tracer.start_as_current_span(operation) as span:
        for k, v in attributes.items():
            span.set_attribute(k, str(v))
        ctx_obj = span.get_span_context()
        trace_id = format(ctx_obj.trace_id, "032x") if ctx_obj.trace_id else None
        span_id = format(ctx_obj.span_id, "016x") if ctx_obj.span_id else None
        yield SpanContext(trace_id=trace_id, span_id=span_id)
