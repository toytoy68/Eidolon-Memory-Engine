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
import json
import re
import uuid

from core.indexing.port import IndexHit
from core.indexing.worker_canonical import CanonicalReader
from core.retrieval.archive_chunks import chunk_messages, validate_reference

PROJECTION_ID = "archive-passage-v1:1200:160"
_NAMESPACE = uuid.UUID("5b7f0a52-6a8e-4c39-9f5e-2b3c1d7e9a10")


def point_id(information_id, revision, digest, reference):
    """Deterministic point identity. Fields are validated, then serialized as a JSON array, so no value
    can absorb a separator of its neighbour, and 1, 1.0 and True cannot name the same passage twice."""
    if type(information_id) is not str or not re.fullmatch(r"[A-Za-z0-9._-]+", information_id):
        raise ValueError("invalid information identity")
    if type(revision) is not int or revision < 1:
        raise ValueError("invalid revision")
    if type(digest) is not str or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("invalid canonical digest")
    validate_reference(reference)
    key = json.dumps([PROJECTION_ID, information_id, revision, digest, reference["message_index"],
                      reference["start"], reference["end"]], separators=(",", ":"))
    return str(uuid.uuid5(_NAMESPACE, key))


class ProjectionBudgetExceeded(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _budget(value):
    if value is not None and (type(value) is not int or value < 1):
        raise ValueError("invalid projection budget")
    return value


class ArchivePassageProjection:
    """Index side: project one canonical archive into passage points (payload = proof + offsets).

    G258-9 budgets, both optional and supplied by the operator: max_passages_per_archive bounds one
    projection; max_points bounds everything STORED, superseded points included, because nothing here
    deletes them. A refused projection changes nothing: the previous projection stays served."""

    def __init__(self, persistent_root, *, score, max_points=None, max_passages_per_archive=None):
        self.root, self.score, self.points = persistent_root, score, {}
        self.max_points, self.max_passages = _budget(max_points), _budget(max_passages_per_archive)
        # information_id -> (revision, digest) of its last successful projection, or None when the last
        # attempt could not read it (revoked, absent, unreadable). Older points are kept, never served.
        self.current = {}

    def project(self, information_id):
        try:
            memory, digest = CanonicalReader(self.root)(information_id)
        except Exception:
            self.current[information_id] = None
            raise
        staged = {}
        for chunk in chunk_messages(memory.content, max_chars=1200, overlap=160):
            if not chunk.text.strip():
                continue  # whitespace carries no evidence to rank
            pid = point_id(information_id, memory.revision, digest, chunk.reference)
            staged[pid] = dict(kind="passage", information_id=information_id, revision=memory.revision,
                               canonical_sha256=digest, projection_id=PROJECTION_ID,
                               passage=dict(chunk.reference),
                               _vector_text=sha256(chunk.text.encode()).hexdigest())  # stand-in, no text
            if self.max_passages is not None and len(staged) > self.max_passages:
                raise ProjectionBudgetExceeded("PASSAGES_PER_ARCHIVE")
        new = sum(1 for pid in staged if pid not in self.points)  # re-projecting the same bytes costs nothing
        if self.max_points is not None and len(self.points) + new > self.max_points:
            raise ProjectionBudgetExceeded("POINTS")
        self.points.update(staged)
        self.current[information_id] = (memory.revision, digest)
        return tuple(staged)

    def stats(self):
        """What the operator needs to decide a (reviewed, separate) compaction; nothing is removed here."""
        served = sum(1 for p in self.points.values() if self._served(p))
        return dict(points=len(self.points), served=served, superseded=len(self.points) - served,
                    archives=len(self.current), unservable=sum(1 for v in self.current.values() if v is None))

    def _served(self, point):
        return self.current.get(point["information_id"]) == (point["revision"], point["canonical_sha256"])

    def query(self, text, *, limit):
        # Superseded points would otherwise fill the candidate limit and hide the current passages.
        served = [kv for kv in self.points.items() if self._served(kv[1])]
        ranked = sorted(served, key=lambda kv: (-self.score(text, kv[1]), kv[0]))[:limit]
        return [IndexHit(p["information_id"], float(self.score(text, p)),
                         {"revision": p["revision"], "canonical_sha256": p["canonical_sha256"],
                          "policy": "claude-archive-passage-experiment", "projection_id": p["projection_id"],
                          "index_freshness": "UNVERIFIED_INCREMENTAL", "passage": dict(p["passage"])})
                for _, p in ranked]
