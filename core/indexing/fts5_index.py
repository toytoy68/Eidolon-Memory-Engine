# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/indexing/fts5_index.py
# Description : Derived SQLite FTS5 IndexPort, candidate generator for lexical_v1.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Derived SQLite FTS5 index behind the existing IndexPort (C198 proposal).

FTS5 (BM25) only *selects candidates*; the final score is the same
``lexical_ranking`` as the reference ``InMemoryIndex``, so swapping adapters does
not change ranking semantics. The canonical Markdown files stay the only truth:
writes reach this index through the change journal and worker like Qdrant, and
``rebuild`` builds a new database next to the old one and swaps it with
``os.replace``, so a failed rebuild leaves the previous index usable.
Not wired into any runtime by this module.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3

from core.backend.errors import InvalidMemory
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.indexing.manifest import build_manifest
from core.indexing.port import IndexHit, IndexPort, IndexStatus
from core.retrieval.ranking import lexical_ranking, terms

SCHEMA = "eidolon-fts5-index/1"


def _text(value) -> str:
    """Values only, never JSON key names (keys would match every document)."""
    if isinstance(value, str):
        return value
    if type(value) in (int, float):
        return str(value)
    if isinstance(value, dict):
        return " ".join(_text(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return " ".join(_text(v) for v in value)
    return ""


class SqliteFts5Index(IndexPort):
    def __init__(self, path: Path, *, candidate_floor: int = 500, candidate_factor: int = 50) -> None:
        self.path = Path(path)
        if self.path.is_symlink() or self.path.parent.is_symlink():
            raise ValueError("FTS5 index path must not be a symlink")
        if not self.path.parent.is_dir():
            raise ValueError("FTS5 index parent must be an existing directory")
        if type(candidate_floor) is not int or type(candidate_factor) is not int \
                or candidate_floor < 1 or candidate_factor < 1:
            raise ValueError("invalid candidate budget")
        self.candidate_floor, self.candidate_factor = candidate_floor, candidate_factor
        self._initialise(self.path)

    # -- storage -------------------------------------------------------------------------
    @staticmethod
    @contextmanager
    def _open(path: Path):
        fresh = not path.exists()
        if fresh:                                    # private from the first byte
            os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
        connection = sqlite3.connect(path, timeout=30)
        try:
            connection.execute("PRAGMA busy_timeout=30000")
            with connection:
                yield connection
        finally:
            connection.close()

    @classmethod
    def _initialise(cls, path: Path) -> None:
        with cls._open(path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
            row = db.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
            if row is None:
                db.execute("INSERT INTO meta VALUES ('schema', ?)", (SCHEMA,))
            elif row[0] != SCHEMA:
                raise ValueError("incompatible FTS5 index schema")
            db.execute("CREATE TABLE IF NOT EXISTS documents (information_id TEXT PRIMARY KEY, memory TEXT NOT NULL)")
            db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5("
                       "information_id UNINDEXED, content, auxiliary, "
                       "tokenize='unicode61 remove_diacritics 0')")

    @staticmethod
    def _put(db: sqlite3.Connection, memory: Memory) -> None:
        db.execute("DELETE FROM fts WHERE information_id=?", (memory.information_id,))
        db.execute("INSERT OR REPLACE INTO documents VALUES (?, ?)",
                   (memory.information_id, json.dumps(asdict(memory), ensure_ascii=False, sort_keys=True)))
        auxiliary = " ".join((memory.information_id, _text(memory.metadata), _text(memory.provenance),
                              _text(memory.temporal), _text(memory.verification), _text(memory.relations)))
        db.execute("INSERT INTO fts VALUES (?, ?, ?)",
                   (memory.information_id, _text(memory.content), auxiliary))

    # -- IndexPort -----------------------------------------------------------------------
    def upsert(self, memory: Memory) -> None:
        with self._open(self.path) as db:
            self._put(db, memory)
            db.execute("DELETE FROM meta WHERE key='source_digest'")

    def delete(self, information_id: str) -> None:
        with self._open(self.path) as db:
            db.execute("DELETE FROM fts WHERE information_id=?", (information_id,))
            db.execute("DELETE FROM documents WHERE information_id=?", (information_id,))
            db.execute("DELETE FROM meta WHERE key='source_digest'")

    def query(self, text: str, *, limit: int = 5) -> list[IndexHit]:
        if type(limit) is not int or limit < 1:
            raise ValueError("limit must be a positive integer")
        wanted = tuple(dict.fromkeys(terms(text)))
        if not wanted:
            return []
        expression = " OR ".join('"' + term.replace('"', '""') + '"' for term in wanted)
        budget = max(self.candidate_floor, limit * self.candidate_factor)
        with self._open(self.path) as db:
            rows = db.execute(
                "SELECT d.memory, bm25(fts) FROM fts JOIN documents d USING (information_id) "
                "WHERE fts MATCH ? ORDER BY bm25(fts) LIMIT ?", (expression, budget)).fetchall()
        hits = []
        for raw, bm25 in rows:
            memory = Memory(**json.loads(raw))
            ranked = lexical_ranking(text, memory.content, memory.information_id, memory.metadata,
                                     (memory.provenance, memory.temporal, memory.verification,
                                      memory.relations))
            if ranked.coverage:
                explanation = ranked.explanation() | {"candidates": "fts5_bm25", "bm25": -float(bm25)}
                hits.append(IndexHit(memory.information_id, ranked.score, explanation))
        return sorted(hits, key=lambda item: (-item.score, item.information_id))[:limit]

    def rebuild(self, persistent_root: Path) -> None:
        root = Path(persistent_root)
        manifest = build_manifest(root)
        staging = self.path.with_name(self.path.name + ".rebuild")
        for suffix in ("", "-wal", "-shm", "-journal"):
            Path(str(staging) + suffix).unlink(missing_ok=True)
        try:
            self._initialise(staging)
            with self._open(staging) as db:
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
                    self._put(db, memory)
                db.execute("INSERT OR REPLACE INTO meta VALUES ('source_digest', ?)", (manifest.digest,))
            # Publish only a standalone complete SQLite image. An outstanding WAL
            # is not part of an atomic rename of the main database file.
            with sqlite3.connect(staging) as validation:
                mode = validation.execute("PRAGMA journal_mode").fetchone()[0]
                if mode == "wal":
                    checkpoint = validation.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                    if checkpoint[0] != 0:
                        raise OSError("FTS5 staging WAL checkpoint busy")
                if validation.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise OSError("FTS5 staging integrity failed")
            descriptor = os.open(staging, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.replace(staging, self.path)                       # atomic swap, old index kept on failure
            if os.name != "nt":                                  # persist the directory entry
                descriptor = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        finally:
            for suffix in ("", "-wal", "-shm", "-journal"):
                Path(str(staging) + suffix).unlink(missing_ok=True)

    def status(self) -> IndexStatus:
        with self._open(self.path) as db:
            documents = db.execute("SELECT count(*) FROM documents").fetchone()[0]
            row = db.execute("SELECT value FROM meta WHERE key='source_digest'").fetchone()
        return IndexStatus(documents, row[0] if row else None)
