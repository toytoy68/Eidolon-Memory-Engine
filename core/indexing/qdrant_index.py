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

from hashlib import sha256
import json
import math
from pathlib import Path
import re
from threading import RLock
from uuid import UUID, uuid4, uuid5

from qdrant_client import models

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.indexing.manifest import build_manifest
from core.indexing.port import IndexHit, IndexPort, IndexStatus
from core.persistence import has_symlink_component


_NAMESPACE = UUID("1328f012-116b-4df9-af89-41204113fe4e")
_META = str(uuid5(_NAMESPACE, "descriptor"))


def _point_id(identity):
    return str(uuid5(_NAMESPACE, "information:" + identity))


class QdrantIndex(IndexPort):
    """One trusted server-selected alias per corpus/access scope.

    ``embedding_id`` must identify model weights AND preprocessing/version.
    Supplying a compatible dimension alone does not establish compatibility.
    ``create=True`` explicitly permits creation of a new isolated index.
    """

    def __init__(self, client, alias: str, *, embed, dimensions: int,
                 embedding_id: str, create: bool = False):
        if not isinstance(alias, str) or not re.fullmatch(r"eidolon_[a-z0-9_]{1,90}", alias):
            raise ValueError("invalid managed alias")
        if type(dimensions) is not int or not 1 <= dimensions <= 65536:
            raise ValueError("invalid embedding dimensions")
        if (not isinstance(embedding_id, str) or not embedding_id.strip()
                or len(embedding_id) > 256 or any(ord(c) < 32 for c in embedding_id)):
            raise ValueError("invalid embedding identity")
        if not callable(embed) or type(create) is not bool:
            raise ValueError("invalid index configuration")
        self.client, self.alias, self.embed = client, alias, embed
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
                "kind": "descriptor", "schema": 1, "alias": self.alias,
                "dimensions": self.dimensions, "embedding_id": self.embedding_id,
                "source_digest": digest})], wait=True)

    def _descriptor(self):
        records = self.client.retrieve(self.alias, ids=[_META], with_payload=True,
                                       with_vectors=False)
        if len(records) != 1:
            raise ValueError("missing index descriptor")
        data = records[0].payload or {}
        if (data.get("kind") != "descriptor" or type(data.get("schema")) is not int
                or data.get("schema") != 1 or data.get("alias") != self.alias
                or type(data.get("dimensions")) is not int
                or data.get("dimensions") != self.dimensions
                or data.get("embedding_id") != self.embedding_id):
            raise ValueError("index embedding or descriptor mismatch")
        digest = data.get("source_digest")
        if digest is not None and (not isinstance(digest, str)
                                   or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise ValueError("invalid source digest")
        config = self.client.get_collection(self.alias).config.params.vectors
        if (not isinstance(config, models.VectorParams) or config.size != self.dimensions
                or config.distance != models.Distance.COSINE):
            raise ValueError("index embedding vector configuration mismatch")
        return data

    def _vector(self, text):
        values = list(self.embed(text))
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

    def _point(self, memory):
        identity = self._identity(memory.information_id)
        if type(memory.revision) is not int or memory.revision < 1:
            raise ValueError("invalid Information revision")
        text = memory.content if isinstance(memory.content, str) else json.dumps(
            memory.content, ensure_ascii=False, sort_keys=True, allow_nan=False)
        return models.PointStruct(id=_point_id(identity), vector=self._vector(text), payload={
            "kind": "information", "information_id": identity,
            "revision": memory.revision, "text_sha256": sha256(text.encode()).hexdigest()})

    @staticmethod
    def _filter():
        return models.Filter(must=[models.FieldCondition(
            key="kind", match=models.MatchValue(value="information"))])

    def upsert(self, memory: Memory) -> None:
        with self._lock:
            self._descriptor()
            point = self._point(memory)
            self._write_descriptor(self.alias, None)
            self.client.upsert(self.alias, points=[point], wait=True)

    def delete(self, information_id: str) -> None:
        with self._lock:
            self._descriptor()
            identity = self._identity(information_id)
            self._write_descriptor(self.alias, None)
            self.client.delete(self.alias, points_selector=models.PointIdsList(
                points=[_point_id(identity)]), wait=True)

    def query(self, text: str, *, limit: int = 5) -> list[IndexHit]:
        if not isinstance(text, str) or type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("invalid query or limit")
        with self._lock:
            self._descriptor()
            if not text.strip():
                return []
            result = self.client.query_points(self.alias, query=self._vector(text),
                query_filter=self._filter(), limit=limit, with_payload=True,
                with_vectors=False)
            hits = []
            for hit in result.points:
                p = hit.payload or {}
                identity = self._identity(p.get("information_id"))
                if (p.get("kind") != "information" or str(hit.id) != _point_id(identity)
                        or type(p.get("revision")) is not int or p["revision"] < 1
                        or not isinstance(p.get("text_sha256"), str)
                        or not re.fullmatch(r"[0-9a-f]{64}", p["text_sha256"])
                        or not math.isfinite(hit.score)):
                    raise ValueError("invalid candidate payload")
                hits.append(IndexHit(identity, hit.score, {
                    "policy": "qdrant_cosine_candidates_v1", "embedding_id": self.embedding_id,
                    "revision": p["revision"], "text_sha256": p["text_sha256"],
                    "canonical_revalidation_required": True}))
            return sorted(hits, key=lambda h: (-h.score, h.information_id))

    def rebuild(self, persistent_root: Path) -> None:
        with self._lock:
            self._descriptor()
            root = Path(persistent_root)
            manifest = build_manifest(root)
            generation = self._generation()
            for entry in manifest.entries:
                path = root / (entry.information_id + ".md")
                if has_symlink_component(path):
                    raise ValueError("index source changed to symlink")
                raw = path.read_bytes()
                if sha256(raw).hexdigest() != entry.file_sha256:
                    raise ValueError("index source changed during rebuild")
                memory = FilesystemBackend._deserialize(raw.decode("utf-8"))
                if memory.information_id != entry.information_id or memory.revision != entry.revision:
                    raise ValueError("index source identity changed")
                self.client.upsert(generation, points=[self._point(memory)], wait=True)
            if build_manifest(root) != manifest:
                raise ValueError("index source changed during rebuild")
            self._write_descriptor(generation, manifest.digest)
            count = self.client.count(generation, count_filter=self._filter(), exact=True).count
            if count != len(manifest.entries):
                raise ValueError("rebuilt index count mismatch")
            self.client.update_collection_aliases([
                models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=self.alias)),
                models.CreateAliasOperation(create_alias=models.CreateAlias(
                    collection_name=generation, alias_name=self.alias))])

    def status(self) -> IndexStatus:
        with self._lock:
            descriptor = self._descriptor()
            count = self.client.count(self.alias, count_filter=self._filter(), exact=True).count
            return IndexStatus(count, descriptor["source_digest"])
