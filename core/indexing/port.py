# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/indexing/port.py
# Description : Contract for a disposable index derived from canonical Information files.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Contract for a disposable index derived from canonical Information files."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from core.backend.models import Memory


@dataclass(frozen=True)
class IndexHit:
    information_id: str
    score: float
    ranking: dict


@dataclass(frozen=True)
class IndexStatus:
    documents: int
    source_digest: str | None
    policy: str = "derived_rebuildable"


class IndexPort(ABC):
    """Adapters must pass tests/contracts/index_port_contract.py unchanged."""

    @abstractmethod
    def upsert(self, memory: Memory) -> None:
        """Update a derived copy of one canonical Information."""

    @abstractmethod
    def delete(self, information_id: str) -> None:
        """Remove a derived entry; repeating the removal is allowed."""

    @abstractmethod
    def query(self, text: str, *, limit: int = 5) -> list[IndexHit]:
        """Return ranked identities with explanations, without changing files."""

    @abstractmethod
    def rebuild(self, persistent_root: Path) -> None:
        """Replace derived state from a stopped canonical file snapshot."""

    @abstractmethod
    def status(self) -> IndexStatus:
        """Expose document count and the last full source digest."""
