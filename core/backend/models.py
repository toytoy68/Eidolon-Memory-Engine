"""Common data models for the Memory Backend."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Memory:
    """Canonical memory object exchanged with a backend."""

    information_id: str
    revision: int = 1
    content: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    temporal: dict[str, Any] = field(default_factory=dict)
    verification: dict[str, Any] = field(default_factory=dict)
    relations: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class StoreResult:
    """Result of a successful store operation."""

    information_id: str
    revision: int


@dataclass
class UpdateResult:
    """Result of a successful update operation."""

    information_id: str
    previous_revision: int
    revision: int


@dataclass
class DeleteResult:
    """Result of a delete request or delete decision."""

    information_id: str
    status: str


@dataclass
class SearchResult:
    """Generic backend search result."""

    memory: Memory
    score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
