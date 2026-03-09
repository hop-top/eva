# tests/unit/test_adapters.py
"""Tests for core/adapters.py ABCs and Span dataclass."""
import pytest
from core.adapters import Span, StorageAdapter, StateAdapter, OtelAdapter


def test_span_set_attribute():
    span = Span(name="test")
    span.set_attribute("k", "v")
    assert span.attributes["k"] == "v"


def test_span_end_is_noop():
    span = Span(name="test")
    span.end()  # must not raise


def test_span_default_attributes():
    span = Span(name="test")
    assert span.attributes == {}


def test_storage_adapter_is_abstract():
    with pytest.raises(TypeError):
        StorageAdapter()  # type: ignore[abstract]


def test_state_adapter_is_abstract():
    with pytest.raises(TypeError):
        StateAdapter()  # type: ignore[abstract]


def test_otel_adapter_is_abstract():
    with pytest.raises(TypeError):
        OtelAdapter()  # type: ignore[abstract]
