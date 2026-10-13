# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/indexing/change_journal.py
# Description : Durable advisory intent journal for asynchronous index workers.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Advisory journal only: filesystem canon and SQLite cannot commit atomically.

Call begin() BEFORE publishing the canonical file, and published() AFTER.
A worker must re-read and validate canonical content before applying any intent.
Manifest reconciliation is mandatory to recover missing or interrupted intents.
This module neither mutates canonical Markdown nor writes to Qdrant.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sqlite3
import time

_ID = re.compile(r"[A-Za-z0-9._-]{1,256}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class ChangeIntent:
    sequence: int
    information_id: str
    revision: int
    operation: str
    canonical_sha256: str | None
    state: str


class ChangeJournal:
    def __init__(self, path: str | Path):
        self.path = str(path)
        # WAL is not a substitute for backups or canonical reconciliation.
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS intents (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                information_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                operation TEXT NOT NULL,
                canonical_sha256 TEXT,
                state TEXT NOT NULL CHECK(state IN ('INTENT','PUBLISHED','INDEXED')),
                created REAL NOT NULL,
                updated REAL NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS intent_state_seq ON intents(state,seq)")

    def _db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("PRAGMA busy_timeout=10000")
        db.execute("PRAGMA synchronous=FULL")
        return db

    def begin(self, information_id: str, revision: int, operation: str,
              canonical_sha256: str | None = None) -> int:
        if (type(information_id) is not str or _ID.fullmatch(information_id) is None
                or type(revision) is not int or revision < 1
                or operation not in ("UPSERT", "DELETE")
                or (operation == "UPSERT" and
                    (type(canonical_sha256) is not str or _DIGEST.fullmatch(canonical_sha256) is None))
                or (operation == "DELETE" and canonical_sha256 is not None)):
            raise ValueError("invalid canonical change intent")
        now = time.time()
        with self._db() as db:
            cur = db.execute(
                "INSERT INTO intents(information_id,revision,operation,canonical_sha256,state,created,updated) VALUES (?,?,?,?,?,?,?)",
                (information_id, revision, operation, canonical_sha256, "INTENT", now, now))
            return int(cur.lastrowid)

    def _advance(self, sequence: int, before: str, after: str) -> None:
        if type(sequence) is not int or sequence < 1:
            raise ValueError("invalid sequence")
        with self._db() as db:
            row = db.execute("SELECT state FROM intents WHERE seq=?", (sequence,)).fetchone()
            if row is None:
                raise ValueError("unknown intent")
            if row[0] == after:
                return
            if row[0] != before:
                raise ValueError("invalid state transition")
            db.execute("UPDATE intents SET state=?,updated=? WHERE seq=?",
                       (after, time.time(), sequence))

    def published(self, sequence: int) -> None:
        """Call only after the canonical rename and its durability checks."""
        self._advance(sequence, "INTENT", "PUBLISHED")

    def indexed(self, sequence: int) -> None:
        """Call only after the worker revalidates canonical revision and index ack."""
        self._advance(sequence, "PUBLISHED", "INDEXED")

    def pending(self, limit: int = 100) -> tuple[ChangeIntent, ...]:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("invalid limit")
        with self._db() as db:
            rows = db.execute("""SELECT seq,information_id,revision,operation,canonical_sha256,state
                                 FROM intents WHERE state != 'INDEXED' ORDER BY seq LIMIT ?""",
                              (limit,)).fetchall()
        return tuple(ChangeIntent(*row) for row in rows)
