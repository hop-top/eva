"""Unit tests for eva-otlp exporter (mocked opentelemetry)."""
import pytest
from unittest.mock import patch, MagicMock


def test_otlp_exporter_imports():
    from eva_otlp.exporter import OtlpExporter
    assert OtlpExporter is not None


def test_otlp_exporter_default_endpoint():
    from eva_otlp.exporter import OtlpExporter
    exp = OtlpExporter()
    assert exp.endpoint == "http://localhost:4317"


def test_otlp_exporter_custom_endpoint():
    from eva_otlp.exporter import OtlpExporter
    exp = OtlpExporter(endpoint="http://otel:4317")
    assert exp.endpoint == "http://otel:4317"


def test_otlp_setup_calls_set_tracer_provider():
    from eva_otlp.exporter import OtlpExporter
    with patch("eva_otlp.exporter.OTLPSpanExporter") as MockExp, \
         patch("eva_otlp.exporter.TracerProvider") as MockProv, \
         patch("eva_otlp.exporter.trace") as mock_trace:
        MockProv.return_value = MagicMock()
        exp = OtlpExporter(endpoint="http://collector:4317")
        exp.setup()
        MockExp.assert_called_once_with(endpoint="http://collector:4317")
        mock_trace.set_tracer_provider.assert_called_once()
