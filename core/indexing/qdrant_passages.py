# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/indexing/qdrant_passages.py
# Description : Durable canonical archive passages with isolated projection descriptor
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Staged archive passage projection, separate from the document-worker index.

Reuses Qdrant descriptor/generation transport, with a distinct projection identity.
Supports query and explicit full reconstruction only. Incremental workers,
upsert and delete are refused. Old/failed generations are retained. One writer
and a stopped canonical copy are required; alias observation is not a lease.
The query limit counts passages; recall selects at most one passage per document.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from uuid import UUID,uuid5
from qdrant_client import models

from core.indexing.qdrant_index import QdrantIndex, _point_id
from core.indexing.port import IndexHit,IndexIncompatible
from core.indexing.query_snapshot import IndexQuerySnapshot
from core.indexing.manifest import build_bounded_manifest
from core.indexing.worker_canonical import CanonicalReader
from core.persistence import exclusive_write
from core.sources.chatgpt_import import is_conversation_archive
from core.retrieval.archive_chunks import chunk_messages,validate_reference

_NAMESPACE=UUID("5b7f0a52-6a8e-4c39-9f5e-2b3c1d7e9a10")
PROJECTION="archive-passage-v2:1200:160:document-json-v1"
MAX_POINTS=100000


def passage_id(identity,revision,digest,reference):
    validate_reference(reference)
    value=[PROJECTION,identity,revision,digest,reference]
    return str(uuid5(_NAMESPACE,json.dumps(value,sort_keys=True,separators=(",",":"))))

@dataclass(frozen=True)
class PassageStatus:
    points: int
    source_digest: str | None
    policy: str="derived_passages_copy_on_write_incremental"

class QdrantPassageIndex(QdrantIndex):
    projection_id=PROJECTION

    def _refuse_incremental(self,*args,**kwargs):
        raise IndexIncompatible("passage index requires an explicit full rebuild; no document worker")

    upsert=_refuse_incremental
    upsert_verified=_refuse_incremental
    delete=_refuse_incremental
    inventory_page=_refuse_incremental
    evidence_for=_refuse_incremental

    def rebuild(self,persistent_root):
        return self._publish(persistent_root, reuse=False)

    def sync(self, persistent_root, *, authorize=None, should_continue=None):
        """Embed changed documents only, publish a complete copy-on-write snapshot.

        Existing vectors are copied, never re-embedded. Canonical inventory and
        vector copying remain O(N); this is not a constant-time document worker.
        Single cooperating writer and stable canonical lock are required, as for
        rebuild. Failed generations are retained and never become visible.
        """
        return self._publish(persistent_root, reuse=True, authorize=authorize, should_continue=should_continue)

    def _publish(self,persistent_root, *, reuse, authorize=None, should_continue=None):
        def check_idle():
            if should_continue is not None and should_continue() is not True:
                raise InterruptedError("maintenance activity resumed; old alias preserved")
        root=Path(persistent_root)
        check_idle()
        with exclusive_write(root),self._lock:
            original=self.active_generation()
            manifest=build_bounded_manifest(root)
            if authorize is not None and any(not authorize(e.information_id) for e in manifest.entries):
                raise PermissionError("passage source is outside operator allow-list")
            descriptor = self._descriptor()
            if reuse and descriptor["source_digest"] == manifest.digest:
                return {"state": "UNCHANGED", "embedded_documents": 0, "copied_points": 0}
            reader=CanonicalReader(root)
            previous = {}
            if reuse:
                offset = None
                count = 0
                while True:
                    points, offset = self.client.scroll(original, scroll_filter=self._filter(),
                        limit=256, offset=offset, with_payload=True, with_vectors=True)
                    count += len(points)
                    if count > MAX_POINTS:
                        raise ValueError("passage point budget")
                    for point in points:
                        payload = point.payload or {}
                        previous.setdefault(payload.get("information_id"), []).append(point)
                    if offset is None:
                        break
            embedded, copied = 0, 0
            generation=self._generation()
            total=0
            for entry in manifest.entries:
                check_idle()
                memory,digest=reader(entry.information_id)
                if memory.revision!=entry.revision or digest!=entry.file_sha256:
                    raise ValueError("canonical source changed during passage rebuild")
                old = previous.get(entry.information_id, [])
                expected = ({passage_id(entry.information_id, entry.revision, digest, c.reference)
                             for c in chunk_messages(memory.content, max_chars=1200, overlap=160, max_chunks=10000)}
                            if is_conversation_archive(memory) else {_point_id(entry.information_id)})
                reusable = old and {str(p.id) for p in old} == expected and all(
                    p.payload.get("revision") == entry.revision and p.payload.get("canonical_sha256") == digest
                    and p.payload.get("embedding_id") == self.embedding_id
                    and p.payload.get("projection_id") == self.projection_id
                    and p.payload.get("generation") == original for p in old)
                if reusable:
                    if total + len(old) > MAX_POINTS:
                        raise ValueError("passage point budget")
                    for point in old:
                        check_idle()
                        vector = point.vector
                        if (type(vector) is not list or len(vector) != self.dimensions or
                            any(type(v) not in (int, float) or not math.isfinite(v) for v in vector)):
                            raise ValueError("invalid retained vector")
                        self.client.upsert(generation, points=[models.PointStruct(id=point.id,
                            vector=vector, payload=dict(point.payload, generation=generation))], wait=True)
                    total += len(old)
                    copied += len(old)
                    continue
                embedded += 1
                if is_conversation_archive(memory):
                    chunks=chunk_messages(memory.content,max_chars=1200,overlap=160,max_chunks=10000)
                    if total+len(chunks)>MAX_POINTS:
                        raise ValueError("passage point budget")
                    for chunk in chunks:
                        check_idle()
                        point=models.PointStruct(id=passage_id(entry.information_id,entry.revision,digest,chunk.reference),
                            vector=self._vector(chunk.text),payload={"kind":"information",
                                "information_id":entry.information_id,"revision":entry.revision,
                                "canonical_sha256":digest,"embedding_id":self.embedding_id,
                                "generation":generation,"projection_id":self.projection_id,
                                "passage":chunk.reference})
                        self.client.upsert(generation,points=[point],wait=True)
                    total+=len(chunks)
                else:
                    if total==MAX_POINTS:raise ValueError("passage point budget")
                    self.client.upsert(generation,points=[self._point(memory,canonical_sha256=digest,
                        generation=generation)],wait=True)
                    total+=1
            if build_bounded_manifest(root)!=manifest:
                raise ValueError("canonical source changed during passage rebuild")
            self._write_descriptor(generation,manifest.digest)
            if self.client.count(generation,count_filter=self._filter(),exact=True).count!=total:
                raise ValueError("passage count mismatch")
            if self.active_generation()!=original:
                raise ValueError("alias changed during passage rebuild")
            check_idle()
            self.client.update_collection_aliases([
                models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=self.alias)),
                models.CreateAliasOperation(create_alias=models.CreateAlias(collection_name=generation,alias_name=self.alias))])
            return {"state": "PUBLISHED", "embedded_documents": embedded, "copied_points": copied}

    def query_snapshot(self,text,*,limit=5):
        if type(text) is not str or type(limit) is not int or not 1<=limit<=1000:
            raise ValueError("invalid passage query")
        with self._lock:
            generation=self.active_generation();descriptor=self._descriptor()
            hits=[]
            if text.strip():
                vector=self._vector(text,query=True)
                if self.active_generation()!=generation:raise ValueError("alias changed during embedding")
                points=self.client.query_points(generation,query=vector,query_filter=self._filter(),limit=limit,
                    with_payload=True,with_vectors=False).points
                for point in points:
                    p=point.payload or {};identity=self._identity(p.get("information_id"))
                    revision=p.get("revision");digest=p.get("canonical_sha256")
                    if (p.get("kind")!="information" or type(revision) is not int or revision<1
                            or type(digest) is not str or re.fullmatch(r"[0-9a-f]{64}",digest) is None
                            or p.get("generation")!=generation or p.get("embedding_id")!=self.embedding_id
                            or p.get("projection_id")!=self.projection_id or not math.isfinite(point.score)):
                        raise ValueError("invalid passage provenance")
                    reference=p.get("passage")
                    if "passage" in p:
                        validate_reference(reference)
                        expected=passage_id(identity,revision,digest,reference)
                    else:
                        expected=_point_id(identity)
                    if str(point.id)!=expected:raise ValueError("invalid passage point identity")
                    ranking={"revision":revision,"canonical_sha256":digest,"generation":generation,
                        "embedding_id":self.embedding_id,"projection_id":self.projection_id,
                        "source_digest":descriptor["source_digest"],"policy":"qdrant_archive_candidates_v1",
                        "index_freshness":"FULL_REBUILD_SNAPSHOT" if descriptor["source_digest"] else "UNVERIFIED_INCREMENTAL"}
                    if reference is not None:ranking["passage"]=dict(reference)
                    hits.append(IndexHit(identity,point.score,ranking))
            if self.active_generation()!=generation or self._descriptor()!=descriptor:
                raise ValueError("passage snapshot changed during query")
            return IndexQuerySnapshot(tuple(hits),generation,descriptor["source_digest"])

    def status(self):
        with self._lock:
            descriptor=self._descriptor()
            return PassageStatus(self.client.count(self.alias,count_filter=self._filter(),exact=True).count,
                                 descriptor["source_digest"])
