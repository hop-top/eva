# core/adapters.py
"""Abstract base classes for pluggable adapters."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.case_results import CaseResult


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


class CaseResultStore(ABC):
    """Durable per-case results, keyed (dataset, target_id, case, case_hash).

    Separate from ``StorageAdapter`` so existing adapters are unaffected.
    """

    @abstractmethod
    def put_case_results(self, records: "list[CaseResult]") -> int:
        """Insert records whose key is absent; existing keys are left
        untouched (first result stands). Returns the number inserted."""

    @abstractmethod
    def get_case_results(
        self,
        dataset: str,
        target_id: str | None = None,
        case_ids: list[str] | None = None,
    ) -> "list[CaseResult]":
        """Records for a dataset, optionally for one target and some cases,
        ordered by (target_id, case, case_hash, at, run_id)."""

    @abstractmethod
    def replace_case_result(self, record: "CaseResult") -> None:
        """Overwrite the record at ``record.key``. Only for resolving an
        import conflict in favour of the earlier result."""


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
