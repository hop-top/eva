# core/otel.py
"""OTEL adapter implementations: NoopOtelAdapter and StdoutOtelAdapter."""
from __future__ import annotations

import json
import sys
from typing import Any

from core.adapters import OtelAdapter, Span


class NoopSpan(Span):
    """A span that silently discards all telemetry."""

    def end(self) -> None:
        pass


class NoopOtelAdapter(OtelAdapter):
    """OtelAdapter that does nothing — useful for tests and local dev."""

    def start_span(
        self, name: str, attributes: dict[str, Any] | None = None
    ) -> NoopSpan:
        return NoopSpan(name=name, attributes=attributes or {})


class StdoutSpan(Span):
    """A span that emits JSON to stdout on end()."""

    def end(self) -> None:
        print(
            json.dumps({"span": self.name, "attributes": self.attributes}),
            file=sys.stdout,
        )


class StdoutOtelAdapter(OtelAdapter):
    """OtelAdapter that prints span data to stdout as JSON."""

    def start_span(
        self, name: str, attributes: dict[str, Any] | None = None
    ) -> StdoutSpan:
        return StdoutSpan(name=name, attributes=attributes or {})
