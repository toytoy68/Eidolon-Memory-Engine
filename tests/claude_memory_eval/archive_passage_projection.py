# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/archive_passage_projection.py
# Description : Projection EXPÉRIMENTALE des passages d'archives pour l'index (Claude, G252-10)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""EXPERIMENTAL, test-only, in-memory: the minimal contract a production Qdrant adapter would implement for
archive passages (proposal: Core docs/proposals/2026-10-15-archive-passages-slice.md). No Qdrant, no model,
no private corpus. Points carry NO text: the cited excerpt is always resolved from canonical bytes."""
from hashlib import sha256
import uuid

from core.indexing.port import IndexHit
from core.indexing.worker_canonical import CanonicalReader
from core.retrieval.archive_chunks import chunk_messages

PROJECTION_ID = "archive-passage-v1:1200:160"
_NAMESPACE = uuid.UUID("5b7f0a52-6a8e-4c39-9f5e-2b3c1d7e9a10")


def point_id(information_id, revision, digest, reference):
    key = f"{PROJECTION_ID}:{information_id}:{revision}:{digest}:" \
          f"{reference['message_index']}:{reference['start']}:{reference['end']}"
    return str(uuid.uuid5(_NAMESPACE, key))


class ArchivePassageProjection:
    """Index side: project one canonical archive into passage points (payload = proof + offsets)."""

    def __init__(self, persistent_root, *, score):
        self.root, self.score, self.points = persistent_root, score, {}

    def project(self, information_id):
        memory, digest = CanonicalReader(self.root)(information_id)
        added = []
        for chunk in chunk_messages(memory.content, max_chars=1200, overlap=160):
            pid = point_id(information_id, memory.revision, digest, chunk.reference)
            self.points[pid] = dict(kind="passage", information_id=information_id, revision=memory.revision,
                                    canonical_sha256=digest, projection_id=PROJECTION_ID,
                                    passage=dict(chunk.reference),
                                    _vector_text=sha256(chunk.text.encode()).hexdigest())  # stand-in, no text
            added.append(pid)
        return tuple(added)

    def query(self, text, *, limit):
        ranked = sorted(self.points.items(), key=lambda kv: (-self.score(text, kv[1]), kv[0]))[:limit]
        return [IndexHit(p["information_id"], float(self.score(text, p)),
                         {"revision": p["revision"], "canonical_sha256": p["canonical_sha256"],
                          "policy": "claude-archive-passage-experiment", "projection_id": p["projection_id"],
                          "index_freshness": "UNVERIFIED_INCREMENTAL", "passage": dict(p["passage"])})
                for _, p in ranked]
