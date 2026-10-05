# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/indexing/memory_index.py
# Description : Dependency-free reference implementation of the derived IndexPort.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Dependency-free reference implementation of the derived IndexPort."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path

from core.backend.errors import InvalidMemory
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.indexing.manifest import build_manifest
from core.indexing.port import IndexHit, IndexPort, IndexStatus
from core.retrieval.ranking import lexical_ranking


class InMemoryIndex(IndexPort):
    def __init__(self) -> None:
        self._documents: dict[str, Memory] = {}
        self._source_digest: str | None = None

    def upsert(self, memory: Memory) -> None:
        self._documents[memory.information_id] = deepcopy(memory)
        self._source_digest = None

    def delete(self, information_id: str) -> None:
        self._documents.pop(information_id, None)
        self._source_digest = None

    def query(self, text: str, *, limit: int = 5) -> list[IndexHit]:
        hits = []
        for memory in self._documents.values():
            ranked = lexical_ranking(text, memory.content, memory.information_id,
                                     memory.metadata, (memory.provenance, memory.temporal,
                                                       memory.verification, memory.relations))
            if ranked.coverage:
                hits.append(IndexHit(memory.information_id, ranked.score, ranked.explanation()))
        return sorted(hits, key=lambda item: (-item.score, item.information_id))[:limit]

    def rebuild(self, persistent_root: Path) -> None:
        root = Path(persistent_root)
        manifest = build_manifest(root)
        next_documents = {}
        for entry in manifest.entries:
            path = root / f"{entry.information_id}.md"
            if path.is_symlink():
                raise InvalidMemory("index source became a symlink")
            raw = path.read_bytes()
            if sha256(raw).hexdigest() != entry.file_sha256:
                raise InvalidMemory("index source changed during rebuild")
            memory = FilesystemBackend._deserialize(raw.decode("utf-8"))
            if memory.information_id != entry.information_id:
                raise InvalidMemory("index source identity changed")
            next_documents[entry.information_id] = memory
        self._documents = next_documents
        self._source_digest = manifest.digest

    def status(self) -> IndexStatus:
        return IndexStatus(len(self._documents), self._source_digest)
