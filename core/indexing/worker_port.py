# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/indexing/worker_port.py
# Description : Restricted verified index capability for maintenance and its children.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Production adoption of Claude's G236-7 experiment, integrated by Codex G253.

The host retains its administrative adapter; the maintenance graph receives this
explicit six-member interface. This is a design boundary, not a sandbox against
malicious Python code in the same process. Permission and provenance checks remain
in the workers. No cached generation, implicit authorization or delete capability.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from .port import IndexEvidence, IndexInventoryPage

if TYPE_CHECKING:
    from core.backend.models import Memory


class WorkerIndexPort(Protocol):
    @property
    def embedding_id(self) -> str: ...

    @property
    def alias(self) -> str: ...

    def active_generation(self) -> str: ...

    def evidence_for(self, information_id: str) -> IndexEvidence | None: ...

    def upsert_verified(self, memory: Memory, *, canonical_sha256: str) -> IndexEvidence: ...

    def inventory_page(self, *, generation: str, offset: str | None = None,
                       limit: int = 100) -> IndexInventoryPage: ...


class WorkerIndexView:
    __slots__ = ("_adapter",)

    def __init__(self, adapter: WorkerIndexPort):
        object.__setattr__(self, "_adapter", adapter)

    def __setattr__(self, name, value):
        raise AttributeError("the worker index port is read-only")

    def __delattr__(self, name):
        raise AttributeError("the worker index port is read-only")

    @property
    def embedding_id(self):
        return self._adapter.embedding_id

    @property
    def alias(self):
        return self._adapter.alias

    def active_generation(self):
        return self._adapter.active_generation()

    def evidence_for(self, information_id):
        return self._adapter.evidence_for(information_id)

    def upsert_verified(self, memory, *, canonical_sha256):
        return self._adapter.upsert_verified(memory, canonical_sha256=canonical_sha256)

    def inventory_page(self, *, generation, offset=None, limit=100):
        return self._adapter.inventory_page(generation=generation, offset=offset, limit=limit)
