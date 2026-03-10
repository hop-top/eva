import pytest
from unittest.mock import patch, MagicMock


def test_otlp_exporter_imports():
    from eva_otlp.exporter import OtlpExporter
    assert OtlpExporter is not None


def test_otlp_exporter_configures_endpoint():
    from eva_otlp.exporter import OtlpExporter
    exporter = OtlpExporter(endpoint="http://localhost:4317")
    assert exporter.endpoint == "http://localhost:4317"


def test_otlp_exporter_default_endpoint():
    from eva_otlp.exporter import OtlpExporter
    exporter = OtlpExporter()
    assert exporter.endpoint == "http://localhost:4317"


def test_otlp_exporter_setup_registers_provider():
    """setup() installs a TracerProvider with OTLP exporter."""
    from eva_otlp.exporter import OtlpExporter

    with patch("eva_otlp.exporter.OTLPSpanExporter") as MockExporter, \
         patch("eva_otlp.exporter.TracerProvider") as MockProvider, \
         patch("eva_otlp.exporter.trace") as mock_trace:

        MockProvider.return_value = MagicMock()
        exporter = OtlpExporter(endpoint="http://collector:4317")
        exporter.setup()

        MockExporter.assert_called_once_with(endpoint="http://collector:4317")
        mock_trace.set_tracer_provider.assert_called_once()
