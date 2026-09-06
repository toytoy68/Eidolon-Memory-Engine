from __future__ import annotations
"""Abstract interface implemented by Memory backends."""

from abc import ABC, abstractmethod
from typing import Any

from .models import DeleteResult, Memory, SearchResult, StoreResult, UpdateResult


class MemoryBackend(ABC):
    """Technology-independent interface for persistent memory storage."""

    @abstractmethod
    def store(self, memory: Memory) -> StoreResult:
        """Create a new memory."""

    @abstractmethod
    def get(self, information_id: str) -> Memory | None:
        """Retrieve a memory by identifier."""

    @abstractmethod
    def exists(self, information_id: str) -> bool:
        """Return whether a memory exists."""

    @abstractmethod
    def update(
        self,
        information_id: str,
        memory: Memory,
        previous_revision: int,
    ) -> UpdateResult:
        """Update a memory using optimistic revision control."""

    @abstractmethod
    def delete_request(
        self,
        information_id: str,
        requested_by: str,
        reason: str,
        revision: int,
        operation_id: str,
    ) -> DeleteResult:
        """Create a pending deletion request."""

    @abstractmethod
    def approve_delete(
        self,
        information_id: str,
        operation_id: str,
    ) -> DeleteResult:
        """Approve a pending deletion."""

    @abstractmethod
    def cancel_delete(
        self,
        information_id: str,
        operation_id: str,
    ) -> DeleteResult:
        """Cancel a pending deletion."""

    @abstractmethod
    def list(
        self,
        offset: int = 0,
        limit: int = 100,
        filters: dict[str, Any] | None = None,
    ) -> list[Memory]:
        """List memories."""

    @abstractmethod
    def search(
        self,
        query: str,
        options: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Search memories."""

    @abstractmethod
    def rebuild_index(self) -> dict[str, Any]:
        """Rebuild any derived search index from canonical storage."""
