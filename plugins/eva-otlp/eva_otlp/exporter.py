from __future__ import annotations
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter


class OtlpExporter:
    """
    OTLP trace exporter for Eva.
    Pipes Eva spans to any OTEL-compatible backend (Jaeger, Datadog, Grafana Tempo).

    Usage:
        from eva_otlp.exporter import OtlpExporter
        exporter = OtlpExporter(endpoint="http://collector:4317")
        exporter.setup()  # Call once at startup — installs the global TracerProvider
    """

    def __init__(self, endpoint: str = "http://localhost:4317") -> None:
        self.endpoint = endpoint

    def setup(self) -> None:
        otlp_exporter = OTLPSpanExporter(endpoint=self.endpoint)
        provider = TracerProvider()
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        trace.set_tracer_provider(provider)
