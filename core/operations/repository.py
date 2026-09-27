"""Repository contract for persistent Operations."""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.operations.models import OperationRecord


class OperationRepository(ABC):
    """Abstract persistence contract for Operation records."""

    @abstractmethod
    def create(self, operation: OperationRecord) -> None:
        """Persist a new operation record."""

    @abstractmethod
    def get(self, operation_id: str) -> OperationRecord | None:
        """Return an operation record by ID, or None if absent."""

    @abstractmethod
    def update(self, operation: OperationRecord) -> None:
        """Persist the updated state of an existing operation."""

    @abstractmethod
    def list_incomplete(self) -> list[OperationRecord]:
        """Return operations that still require recovery."""
