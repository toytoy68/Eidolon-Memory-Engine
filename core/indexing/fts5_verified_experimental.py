"""Experimental provenance-aware FTS5 worker adapter; NOT production-wired.

This keeps verified evidence in the same SQLite transaction as the candidate
document and uses an explicit generation for rebuild fencing. Caller still
owns canonical verification, the journal lock, authorization and replay.
"""
from __future__ import annotations

from hashlib import sha256
import re
from uuid import uuid4

from core.indexing.fts5_index import SqliteFts5Index
from core.indexing.port import IndexEvidence, IndexRecord, IndexInventoryPage, IndexIncompatible

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9._-]{1,256}\Z")


class VerifiedSqliteFts5Index(SqliteFts5Index):
    embedding_id = "fts5-lexical-v1"
    """No embedding weights: identity describes the lexical projection."""
    
    def __init__(self, path, *, alias: str, **kwargs):
        if not re.fullmatch(r"eidolon_[a-z0-9_]{1,90}", alias):
            raise ValueError("invalid managed alias")
        self.alias = alias
        super().__init__(path, **kwargs)
        self._ensure_verified_schema()

    def _ensure_verified_schema(self):
        with self._open(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS verified (information_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, digest TEXT NOT NULL, generation TEXT NOT NULL)")
            identity = db.execute("SELECT value FROM meta WHERE key='worker_alias'").fetchone()
            if identity and identity[0] != self.alias:
                raise IndexIncompatible("FTS5 alias mismatch")
            if not identity:
                db.execute("INSERT INTO meta VALUES ('worker_alias', ?)", (self.alias,))
            row = db.execute("SELECT value FROM meta WHERE key='generation'").fetchone()
            if row is None:
                db.execute("INSERT INTO meta VALUES ('generation', ?)", (self.alias + "__" + uuid4().hex,))

    def active_generation(self):
        with self._open(self.path) as db:
            alias = db.execute("SELECT value FROM meta WHERE key='worker_alias'").fetchone()
            gen = db.execute("SELECT value FROM meta WHERE key='generation'").fetchone()
            if not alias or alias[0] != self.alias or not gen or not gen[0].startswith(self.alias + "__"):
                raise IndexIncompatible("invalid FTS5 generation")
            return gen[0]

    def evidence_for(self, information_id):
        if not isinstance(information_id, str) or not _ID.fullmatch(information_id):
            raise ValueError("invalid identity")
        with self._open(self.path) as db:
            gen = self.active_generation()
            row = db.execute("SELECT revision,digest,generation FROM verified WHERE information_id=?", (information_id,)).fetchone()
            if row is None:
                return None
            revision, digest, written_generation = row
            if type(revision) is not int or revision < 1 or not _DIGEST.fullmatch(digest) or written_generation != gen:
                raise IndexIncompatible("invalid point evidence")
            document = db.execute("SELECT memory FROM documents WHERE information_id=?", (information_id,)).fetchone()
            if document is None:
                raise IndexIncompatible("orphaned evidence")
            import json
            try:
                payload = json.loads(document[0])
            except (ValueError, TypeError) as exc:
                raise IndexIncompatible("invalid indexed document") from exc
            if (type(payload) is not dict or payload.get("information_id") != information_id
                    or type(payload.get("revision")) is not int
                    or payload["revision"] != revision):
                raise IndexIncompatible("evidence does not match indexed document revision")
            return IndexEvidence(information_id, revision, digest, self.embedding_id, gen)

    def upsert_verified(self, memory, *, canonical_sha256):
        if not _ID.fullmatch(memory.information_id) or type(memory.revision) is not int or memory.revision < 1:
            raise ValueError("invalid memory identity/revision")
        if type(canonical_sha256) is not str or not _DIGEST.fullmatch(canonical_sha256):
            raise ValueError("invalid canonical digest")
        with self._open(self.path) as db:
            gen = self.active_generation()
            self._put(db, memory)
            db.execute("INSERT OR REPLACE INTO verified VALUES (?,?,?,?)", (memory.information_id, memory.revision, canonical_sha256, gen))
            db.execute("DELETE FROM meta WHERE key='source_digest'")
        return IndexEvidence(memory.information_id, memory.revision, canonical_sha256, self.embedding_id, gen)

    def inventory_page(self, *, generation, offset=None, limit=100):
        if generation != self.active_generation():
            raise IndexIncompatible("generation changed")
        if type(limit) is not int or not 1 <= limit <= 999:
            raise ValueError("invalid limit")
        if offset is not None and (type(offset) is not str or not _ID.fullmatch(offset)):
            raise ValueError("invalid inventory cursor")
        with self._open(self.path) as db:
            rows = db.execute(
                "SELECT information_id, memory FROM documents WHERE information_id > ? ORDER BY information_id LIMIT ?",
                (offset or "", limit + 1),
            ).fetchall()
            result = []
            import json
            for identity, raw in rows[:limit]:
                revision = json.loads(raw)["revision"]
                if type(revision) is not int or revision < 1:
                    raise IndexIncompatible("invalid revision")
                proof = self.evidence_for(identity)
                result.append(IndexRecord(identity, revision, proof))
            next_offset = rows[limit-1][0] if len(rows) > limit else None
            if self.active_generation() != generation:
                raise IndexIncompatible("generation changed during inventory")
            return IndexInventoryPage(generation, tuple(result), next_offset)

    def delete(self, information_id):
        with self._open(self.path) as db:
            db.execute("DELETE FROM verified WHERE information_id=?", (information_id,))
            db.execute("DELETE FROM fts WHERE information_id=?", (information_id,))
            db.execute("DELETE FROM documents WHERE information_id=?", (information_id,))
            db.execute("DELETE FROM meta WHERE key='source_digest'")

    def upsert(self, memory):
        # Ordinary writes do not claim canonical verification.
        with self._open(self.path) as db:
            self._put(db, memory)
            db.execute("DELETE FROM verified WHERE information_id=?", (memory.information_id,))
            db.execute("DELETE FROM meta WHERE key='source_digest'")

    def rebuild(self, persistent_root):
        super().rebuild(persistent_root)
        self._ensure_verified_schema()  # New generation, no evidence from obsolete index.
