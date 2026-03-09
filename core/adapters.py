# core/adapters.py
"""Abstract base classes for pluggable adapters."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Span:
    name: str
    attributes: dict[str, Any] = field(default_factory=dict)

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def end(self) -> None:
        pass


class StorageAdapter(ABC):
    @abstractmethod
    async def save_result(self, result: Any) -> None: ...

    @abstractmethod
    async def load_results(self, run_id: str) -> list[Any]: ...


class StateAdapter(ABC):
    @abstractmethod
    async def get(self, key: str) -> Any: ...

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int | None = None) -> None: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...


class OtelAdapter(ABC):
    @abstractmethod
    def start_span(
        self, name: str, attributes: dict[str, Any] | None = None
    ) -> Span: ...
