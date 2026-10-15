# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/indexing/qdrant_index.py
# Description : Optional disposable Qdrant index with staged reconstruction.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Candidate identities only; callers must revalidate canonical data and access.

An alias requires a single externally coordinated writer. Rebuild requires a
stopped canonical snapshot. Old and failed generations are retained deliberately:
an ambiguous network timeout must never delete a collection an alias may use.
No embedding model is downloaded or selected by this adapter.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import re
from threading import RLock
from uuid import UUID, uuid4, uuid5

from qdrant_client import models

from core.backend.models import Memory
from core.indexing.manifest import build_manifest
from core.indexing.query_snapshot import IndexQuerySnapshot
from core.indexing.port import (IndexEvidence, IndexHit, IndexPort, IndexStatus,
                                IndexRecord, IndexInventoryPage, IndexIncompatible)
from core.persistence import exclusive_write
from core.indexing.worker_canonical import CanonicalReader


_NAMESPACE = UUID("1328f012-116b-4df9-af89-41204113fe4e")
# Fixed by this implementation: one content string (or sorted JSON) per document.
# Passage indexes require a separate adapter/alias and a distinct descriptor.
DOCUMENT_PROJECTION = "information-content-json-v1"

_META = str(uuid5(_NAMESPACE, "descriptor"))


def _point_id(identity):
    return str(uuid5(_NAMESPACE, "information:" + identity))


class QdrantIndex(IndexPort):
    """One trusted server-selected alias per corpus/access scope.

    ``embedding_id`` must identify model weights AND preprocessing/version.
    Supplying a compatible dimension alone does not establish compatibility.
    ``create=True`` explicitly permits creation of a new isolated index.
    Schema 2 binds DOCUMENT_PROJECTION; schema 1 is never silently migrated.
    A legacy index requires a fresh alias and an explicit canonical rebuild.
    """

    projection_id = DOCUMENT_PROJECTION

    def __init__(self, client, alias: str, *, embed, dimensions: int,
                 embedding_id: str, create: bool = False, query_embed=None):
        if not isinstance(alias, str) or not re.fullmatch(r"eidolon_[a-z0-9_]{1,90}", alias):
            raise ValueError("invalid managed alias")
        if type(dimensions) is not int or not 1 <= dimensions <= 65536:
            raise ValueError("invalid embedding dimensions")
        if (not isinstance(embedding_id, str) or not embedding_id.strip()
                or len(embedding_id) > 256 or any(ord(c) < 32 for c in embedding_id)):
            raise ValueError("invalid embedding identity")
        if not callable(embed) or type(create) is not bool or (query_embed is not None and not callable(query_embed)):
            raise ValueError("invalid index configuration")
        self.client, self.alias, self.embed = client, alias, embed
        self.query_embed = query_embed
        self.dimensions, self.embedding_id = dimensions, embedding_id
        self._lock = RLock()
        aliases = {a.alias_name: a.collection_name for a in client.get_aliases().aliases}
        if alias not in aliases:
            if not create:
                raise ValueError("index alias does not exist; explicit create required")
            if client.collection_exists(alias):
                raise ValueError("alias collides with existing collection")
            collection = self._generation()
            self._write_descriptor(collection, None)
            client.update_collection_aliases([models.CreateAliasOperation(
                create_alias=models.CreateAlias(collection_name=collection, alias_name=alias))])
        self._descriptor()

    def _generation(self):
        name = self.alias + "__" + uuid4().hex
        self.client.create_collection(name, vectors_config=models.VectorParams(
            size=self.dimensions, distance=models.Distance.COSINE))
        return name

    def _write_descriptor(self, collection, digest):
        self.client.upsert(collection, points=[models.PointStruct(
            id=_META, vector=[1.0] + [0.0] * (self.dimensions - 1), payload={
                "kind": "descriptor", "schema": 2, "projection_id": self.projection_id, "alias": self.alias,
                "dimensions": self.dimensions, "embedding_id": self.embedding_id,
                "source_digest": digest})], wait=True)

    def _descriptor(self):
        records = self.client.retrieve(self.alias, ids=[_META], with_payload=True,
                                       with_vectors=False)
        if len(records) != 1:
            raise IndexIncompatible("missing index descriptor")
        data = records[0].payload or {}
        if (data.get("kind") != "descriptor" or type(data.get("schema")) is not int
                or data.get("schema") != 2
                or data.get("projection_id") != self.projection_id or data.get("alias") != self.alias
                or type(data.get("dimensions")) is not int
                or data.get("dimensions") != self.dimensions
                or data.get("embedding_id") != self.embedding_id):
            raise IndexIncompatible("index embedding or descriptor mismatch")
        digest = data.get("source_digest")
        if digest is not None and (not isinstance(digest, str)
                                   or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise IndexIncompatible("invalid source digest")
        config = self.client.get_collection(self.alias).config.params.vectors
        if (not isinstance(config, models.VectorParams) or config.size != self.dimensions
                or config.distance != models.Distance.COSINE):
            raise IndexIncompatible("index embedding vector configuration mismatch")
        return data

    def _vector(self, text, *, query=False):
        values = list((self.query_embed if query and self.query_embed is not None else self.embed)(text))
        if len(values) != self.dimensions:
            raise ValueError("embedding dimension mismatch")
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
            raise ValueError("embedding must contain finite real numbers")
        norm = math.hypot(*values)
        if not math.isfinite(norm) or norm == 0:
            raise ValueError("embedding must have a finite nonzero norm")
        return [v / norm for v in values]

    @staticmethod
    def _identity(identity):
        if not isinstance(identity, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", identity):
            raise ValueError("invalid Information identity")
        return identity

    def _point(self, memory, *, canonical_sha256=None, generation=None):
        identity = self._identity(memory.information_id)
        if type(memory.revision) is not int or memory.revision < 1:
            raise ValueError("invalid Information revision")
        text = memory.content if isinstance(memory.content, str) else json.dumps(
            memory.content, ensure_ascii=False, sort_keys=True, allow_nan=False)
        return models.PointStruct(id=_point_id(identity), vector=self._vector(text), payload={
            "kind": "information", "information_id": identity,
            "revision": memory.revision,
            **({"canonical_sha256": canonical_sha256, "embedding_id": self.embedding_id,
                "generation": generation, "projection_id": self.projection_id} if canonical_sha256 is not None else {})})

    def _active_generation(self):
        aliases = {a.alias_name: a.collection_name for a in self.client.get_aliases().aliases}
        generation = aliases.get(self.alias)
        if not isinstance(generation, str) or not generation.startswith(self.alias + "__"):
            raise ValueError("unavailable managed index generation")
        return generation

    def active_generation(self) -> str:
        """Observed managed generation, with a compatible descriptor (not a lease)."""
        with self._lock:
            generation = self._active_generation()
            self._descriptor()
            if self._active_generation() != generation:
                raise ValueError("index generation changed during observation")
            return generation

    def inventory_page(self, *, generation: str, offset=None, limit=100) -> IndexInventoryPage:
        """Scroll one concrete generation, without vectors or a hiding kind filter.

        Cursor exhaustion is not a snapshot: concurrent inserts behind the cursor
        require another pass. Malformed/foreign points refuse the entire page.
        """
        if (type(generation) is not str or not generation
                or type(limit) is not int or not 1 <= limit <= 999):
            raise ValueError("invalid inventory options")
        def token(value):
            if type(value) is not str or str(UUID(value)) != value:
                raise ValueError("invalid inventory cursor")
            return UUID(value).int
        minimum = token(offset) if offset is not None else -1
        with self._lock:
            if self.active_generation() != generation:
                raise ValueError("index generation changed before inventory")
            records, next_offset = self.client.scroll(
                generation, offset=offset, limit=limit, with_payload=True, with_vectors=False)
            if len(records) > limit:
                raise ValueError("oversized inventory page")
            entries, previous = [], minimum - 1
            for record in records:
                position = token(record.id)
                if position < minimum or position <= previous:
                    raise ValueError("unordered inventory page")
                previous = position
                if record.id == _META:
                    continue
                p = record.payload or {}
                ident = self._identity(p.get("information_id"))
                if (len(ident) > 256 or record.id != _point_id(ident)
                        or p.get("kind") != "information"
                        or type(p.get("revision")) is not int or p["revision"] < 1):
                    raise ValueError("invalid inventory point")
                digest = p.get("canonical_sha256")
                evidence = None
                if digest is not None:
                    if (type(digest) is not str or not re.fullmatch(r"[0-9a-f]{64}", digest)
                            or p.get("embedding_id") != self.embedding_id
                            or p.get("generation") != generation
                            or p.get("projection_id") != self.projection_id):
                        raise ValueError("invalid inventory provenance")
                    evidence = IndexEvidence(ident, p["revision"], digest, self.embedding_id, generation)
                entries.append(IndexRecord(ident, p["revision"], evidence))
            if next_offset is not None:
                if not records or token(next_offset) <= max(previous, minimum):
                    raise ValueError("inventory cursor did not advance")
            if self.active_generation() != generation:
                raise ValueError("index generation changed during inventory")
            return IndexInventoryPage(generation, tuple(entries), next_offset)

    def upsert_verified(self, memory: Memory, *, canonical_sha256: str) -> IndexEvidence:
        """Bind trusted canonical bytes to an upsert; caller must read it back."""
        if type(canonical_sha256) is not str or not re.fullmatch(r"[0-9a-f]{64}", canonical_sha256):
            raise ValueError("invalid canonical digest")
        with self._lock:
            generation = self._active_generation()
            self._descriptor()
            point = self._point(memory, canonical_sha256=canonical_sha256, generation=generation)
            self._descriptor()
            if self._active_generation() != generation:
                raise ValueError("index generation changed before write")
            self._write_descriptor(generation, None)
            self.client.upsert(generation, points=[point], wait=True)
            return IndexEvidence(memory.information_id, memory.revision, canonical_sha256,
                                 self.embedding_id, generation)

    def evidence_for(self, information_id: str) -> IndexEvidence | None:
        """Read exact provenance; legacy points without a digest stay unverified."""
        identity = self._identity(information_id)
        with self._lock:
            generation = self._active_generation()
            self._descriptor()
            records = self.client.retrieve(generation, ids=[_point_id(identity)],
                                           with_payload=True, with_vectors=False)
            if self._active_generation() != generation:
                raise ValueError("index generation changed during read-back")
            if not records:
                return None
            if len(records) != 1:
                raise ValueError("ambiguous index read-back")
            record = records[0]
            p = record.payload or {}
            if (str(record.id) != _point_id(identity) or p.get("kind") != "information"
                    or p.get("information_id") != identity
                    or type(p.get("revision")) is not int or p["revision"] < 1):
                raise ValueError("invalid index read-back payload")
            digest = p.get("canonical_sha256")
            if digest is None:
                return None
            if (type(digest) is not str or not re.fullmatch(r"[0-9a-f]{64}", digest)
                    or p.get("embedding_id") != self.embedding_id
                    or p.get("generation") != generation
                    or p.get("projection_id") != self.projection_id):
                raise ValueError("invalid index provenance")
            return IndexEvidence(identity, p["revision"], digest, self.embedding_id, generation)

    @staticmethod
    def _filter():
        return models.Filter(must=[models.FieldCondition(
            key="kind", match=models.MatchValue(value="information"))])

    def upsert(self, memory: Memory) -> None:
        with self._lock:
            generation = self.active_generation()
            point = self._point(memory)
            if self.active_generation() != generation:
                raise ValueError("index generation changed before write")
            self._write_descriptor(generation, None)
            self.client.upsert(generation, points=[point], wait=True)

    def revision_for(self, information_id: str) -> int | None:
        """Read back a specific point, validating its identity and revision.

        This is evidence of the adapter's current observation, not a
        transaction spanning Qdrant and canonical Markdown.
        """
        identity = self._identity(information_id)
        with self._lock:
            self._descriptor()
            records = self.client.retrieve(
                self.alias, ids=[_point_id(identity)],
                with_payload=True, with_vectors=False)
            if not records:
                return None
            if len(records) != 1:
                raise ValueError("ambiguous index read-back")
            record = records[0]
            payload = record.payload or {}
            if (str(record.id) != _point_id(identity)
                    or payload.get("kind") != "information"
                    or payload.get("information_id") != identity
                    or type(payload.get("revision")) is not int
                    or payload["revision"] < 1):
                raise ValueError("invalid index read-back payload")
            return payload["revision"]

    def delete(self, information_id: str) -> None:
        with self._lock:
            self._descriptor()
            identity = self._identity(information_id)
            self._write_descriptor(self.alias, None)
            self.client.delete(self.alias, points_selector=models.PointIdsList(
                points=[_point_id(identity)]), wait=True)

    def query(self, text: str, *, limit: int = 5) -> list[IndexHit]:
        return list(self.query_snapshot(text, limit=limit).hits)

    def query_snapshot(self, text: str, *, limit: int = 5) -> IndexQuerySnapshot:
        """Bind candidates (including an empty batch) to a checked descriptor.

        A generation/digest change during the query is refused. This does not
        serialize other adapter instances: the single-writer contract remains.
        """
        if not isinstance(text, str) or type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("invalid query or limit")
        with self._lock:
            generation = self.active_generation()
            descriptor = self._descriptor()
            if not text.strip():
                if (self.active_generation() != generation or self._descriptor() != descriptor
                        or self._active_generation() != generation):
                    raise ValueError("index snapshot changed during query")
                return IndexQuerySnapshot((), generation, descriptor["source_digest"])
            vector = self._vector(text, query=True)
            if self.active_generation() != generation:
                raise ValueError("index generation changed during query")
            result = self.client.query_points(generation, query=vector,
                query_filter=self._filter(), limit=limit, with_payload=True,
                with_vectors=False)
            if (self.active_generation() != generation or self._descriptor() != descriptor
                        or self._active_generation() != generation):
                raise ValueError("index snapshot changed during query")
            hits = []
            for hit in result.points:
                p = hit.payload or {}
                identity = self._identity(p.get("information_id"))
                if (p.get("kind") != "information" or str(hit.id) != _point_id(identity)
                        or type(p.get("revision")) is not int or p["revision"] < 1
                        or not math.isfinite(hit.score)):
                    raise ValueError("invalid candidate payload")
                proof = {}
                proof_keys = {'canonical_sha256', 'embedding_id', 'generation', 'projection_id'}
                if descriptor["source_digest"] is not None or proof_keys.intersection(p):
                    digest = p.get('canonical_sha256')
                    if (not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest)
                            or p.get('embedding_id') != self.embedding_id
                            or p.get('generation') != generation
                            or p.get('projection_id') != self.projection_id):
                        raise ValueError("invalid candidate proof")
                    proof = {'canonical_sha256': digest, 'generation': generation}
                hits.append(IndexHit(identity, hit.score, {
                    **proof,
                    "policy": "qdrant_cosine_candidates_v1", "embedding_id": self.embedding_id,
                    "projection_id": self.projection_id,
                    "revision": p["revision"], "source_digest": descriptor["source_digest"],
                    "index_freshness": ("FULL_REBUILD_SNAPSHOT" if descriptor["source_digest"]
                                        else "UNVERIFIED_INCREMENTAL"),
                    "canonical_revalidation_required": True}))
            return IndexQuerySnapshot(tuple(sorted(hits, key=lambda h: (-h.score, h.information_id))),
                                      generation, descriptor["source_digest"])

    def rebuild(self, persistent_root: Path) -> None:
        # Lock ordering matches the journal worker: canonical root, then adapter.
        with exclusive_write(Path(persistent_root)), self._lock:
            original_generation = self.active_generation()
            root = Path(persistent_root)
            reader = CanonicalReader(root)
            manifest = build_manifest(root)
            generation = self._generation()
            for entry in manifest.entries:
                memory, digest = reader(entry.information_id)
                if digest != entry.file_sha256 or memory.revision != entry.revision:
                    raise ValueError("index source changed during rebuild")
                self.client.upsert(generation, points=[self._point(
                    memory, canonical_sha256=digest, generation=generation)], wait=True)
            if build_manifest(root) != manifest:
                raise ValueError("index source changed during rebuild")
            self._write_descriptor(generation, manifest.digest)
            count = self.client.count(generation, count_filter=self._filter(), exact=True).count
            if count != len(manifest.entries):
                raise ValueError("rebuilt index count mismatch")
            if self.active_generation() != original_generation:
                raise ValueError("index generation changed during rebuild")
            self.client.update_collection_aliases([
                models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=self.alias)),
                models.CreateAliasOperation(create_alias=models.CreateAlias(
                    collection_name=generation, alias_name=self.alias))])

    def status(self) -> IndexStatus:
        with self._lock:
            descriptor = self._descriptor()
            count = self.client.count(self.alias, count_filter=self._filter(), exact=True).count
            return IndexStatus(count, descriptor["source_digest"])
