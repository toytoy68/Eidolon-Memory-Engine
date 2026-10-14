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
from contextlib import contextmanager, closing
import os
import stat
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
    created: float | None = None


class JournalCapacityExceeded(RuntimeError):
    """Recovery must wait for pending work to drain; no intent was inserted."""


class ChangeJournal:
    def __init__(self, path: str | Path):
        self.path = str(path)
        parent = Path(self.path).parent
        if not parent.is_dir() or parent.is_symlink():
            raise ValueError("journal parent must be an existing private directory")
        if stat.S_IMODE(parent.stat().st_mode) & 0o077:
            raise ValueError("journal directory must not be accessible to others")
        flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC
        fd = os.open(self.path, flags, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
                raise ValueError("journal file must be private and regular")
        finally:
            os.close(fd)
        # WAL is not a substitute for backups or canonical reconciliation.
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            is_new = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='intents'").fetchone() is None
            db.execute("""CREATE TABLE IF NOT EXISTS intents (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                information_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                operation TEXT NOT NULL,
                canonical_sha256 TEXT,
                state TEXT NOT NULL CHECK(state IN ('INTENT','PUBLISHED','INDEXED','ABANDONED','SUPERSEDED')),
                created REAL NOT NULL,
                updated REAL NOT NULL,
                terminal_reason TEXT
            )""")
            if is_new:
                db.execute("CREATE INDEX intent_state_seq ON intents(state,seq)")
            elif db.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name='intent_state_seq'").fetchone() is None:
                raise ValueError("existing journal index missing; explicit repair required")
            if is_new:
                db.execute("PRAGMA user_version=2")

    @contextmanager
    def _db(self):
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            db.execute("PRAGMA busy_timeout=10000")
            db.execute("PRAGMA synchronous=FULL")
            with db:
                yield db

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
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM intents WHERE seq=?", (sequence,)).fetchone()
            if row is None:
                raise ValueError("unknown intent")
            if row[0] == after:
                return
            if row[0] != before:
                raise ValueError("invalid state transition")
            changed = db.execute("UPDATE intents SET state=?,updated=? WHERE seq=? AND state=?",
                                 (after, time.time(), sequence, before))
            if changed.rowcount != 1:
                raise ValueError("concurrent state transition")

    def ensure_upsert_intent(self, information_id: str, revision: int,
                             canonical_sha256: str, *, pending_limit=100) -> int | None:
        """Recover a lost event without duplicating a pending upsert.

        Caller verifies durable canonical bytes and permissions under the writer
        lock. A pending delete, newer revision or same-revision conflict refuses
        the enqueue. Terminal history does not cover a currently missing point.
        """
        if (type(information_id) is not str or _ID.fullmatch(information_id) is None
                or type(revision) is not int or revision < 1
                or type(canonical_sha256) is not str or _DIGEST.fullmatch(canonical_sha256) is None
                or type(pending_limit) is not int or not 1 <= pending_limit <= 999):
            raise ValueError("invalid recovery intent")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("""SELECT seq,revision,operation,canonical_sha256 FROM intents
                               WHERE state IN ('INTENT','PUBLISHED') AND information_id=?
                               ORDER BY seq""", (information_id,)).fetchall()
            if any(op != "UPSERT" or rev > revision or
                   (rev == revision and digest != canonical_sha256) for _, rev, op, digest in rows):
                return None
            for seq, rev, _, digest in rows:
                if rev == revision and digest == canonical_sha256:
                    return seq
            count = db.execute("""SELECT count(*) FROM (SELECT 1 FROM intents
                WHERE state IN ('INTENT','PUBLISHED') LIMIT ?)""", (pending_limit,)).fetchone()[0]
            if count >= pending_limit:
                raise JournalCapacityExceeded("pending journal requires processing or review")
            now = time.time()
            result = db.execute("""INSERT INTO intents
                (information_id,revision,operation,canonical_sha256,state,created,updated)
                VALUES (?,?,'UPSERT',?,'INTENT',?,?)""",
                                (information_id, revision, canonical_sha256, now, now))
            return int(result.lastrowid)

    def published(self, sequence: int) -> None:
        """Call only after the canonical rename and its durability checks."""
        self._advance(sequence, "INTENT", "PUBLISHED")

    def indexed(self, sequence: int) -> None:
        """Call only after the worker revalidates canonical revision and index ack."""
        self._advance(sequence, "PUBLISHED", "INDEXED")

    def advance_verified(self, expected: ChangeIntent, after: str) -> bool:
        """Compare the complete observed intent and advance it atomically.

        Evidence is verified by the caller under the canonical writer lock.
        A changed/removed row returns False, never advances a different intent.
        This does not make SQLite, Markdown and Qdrant one transaction.
        """
        if (type(expected) is not ChangeIntent
                or (expected.state, after) not in
                (("INTENT", "PUBLISHED"), ("PUBLISHED", "INDEXED"))
                or type(expected.sequence) is not int or expected.sequence < 1):
            raise ValueError("invalid verified journal transition")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("""SELECT seq,information_id,revision,operation,
                                canonical_sha256,state,created FROM intents WHERE seq=?""",
                             (expected.sequence,)).fetchone()
            if row is None or ChangeIntent(*row) != expected:
                return False
            db.execute("UPDATE intents SET state=?,updated=? WHERE seq=?",
                       (after, time.time(), expected.sequence))
            return True

    def close_terminal(self, sequence: int, state: str, reason: str) -> None:
        """Close a reconciled intent only on an explicitly migrated v2 journal.

        The caller must verify canonical state before invoking this method.
        No automatic migration and no canonical or Qdrant mutation occur here.
        """
        if (type(sequence) is not int or sequence < 1
                or state not in ("ABANDONED", "SUPERSEDED")
                or type(reason) is not str or not 1 <= len(reason) <= 300
                or any(ord(c) < 32 for c in reason)):
            raise ValueError("invalid terminal transition")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            columns = {r[1] for r in db.execute("PRAGMA table_info(intents)")}
            if "terminal_reason" not in columns:
                raise ValueError("journal v2 migration required")
            row = db.execute("SELECT state,terminal_reason FROM intents WHERE seq=?", (sequence,)).fetchone()
            if row is None:
                raise ValueError("unknown intent")
            if row == (state, reason):
                return
            if row[0] not in ("INTENT", "PUBLISHED"):
                raise ValueError("invalid state transition")
            updated = db.execute(
                "UPDATE intents SET state=?,terminal_reason=?,updated=? WHERE seq=? AND state=?",
                (state, reason, time.time(), sequence, row[0]))
            if updated.rowcount != 1:
                raise ValueError("concurrent state transition")

    def pending(self, limit: int = 100) -> tuple[ChangeIntent, ...]:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("invalid limit")
        with self._db() as db:
            rows = db.execute("""SELECT seq,information_id,revision,operation,canonical_sha256,state,created
                                 FROM intents WHERE state IN ('INTENT','PUBLISHED') ORDER BY seq LIMIT ?""",
                              (limit,)).fetchall()
        return tuple(ChangeIntent(*row) for row in rows)

    def has_pending(self, information_id: str) -> bool:
        """Check one identity without mistaking a bounded pending page for all rows."""
        if type(information_id) is not str or _ID.fullmatch(information_id) is None:
            raise ValueError("invalid Information identity")
        with self._db() as db:
            return db.execute("""SELECT 1 FROM intents WHERE
                state IN ('INTENT','PUBLISHED') AND information_id=? LIMIT 1""",
                              (information_id,)).fetchone() is not None

    def high_watermark(self) -> int:
        """Highest allocated sequence, retained even if terminal rows are compacted."""
        with self._db() as db:
            row = db.execute("SELECT seq FROM sqlite_sequence WHERE name='intents'").fetchone()
            return row[0] if row else 0

    def pending_page(self, *, after: int, through: int, limit=100):
        """Keyset page within an explicit finite pass; no offset or starvation."""
        if (type(after) is not int or type(through) is not int or not 0 <= after <= through
                or type(limit) is not int or not 1 <= limit <= 1000):
            raise ValueError("invalid pending page")
        with self._db() as db:
            rows = db.execute("""SELECT seq,information_id,revision,operation,canonical_sha256,state,created
                FROM intents WHERE state IN ('INTENT','PUBLISHED') AND seq>? AND seq<=?
                ORDER BY seq LIMIT ?""", (after, through, limit)).fetchall()
            return tuple(ChangeIntent(*row) for row in rows)

    def intent(self, sequence: int):
        """Read one current intent for advisory review, including terminal states."""
        if type(sequence) is not int or sequence < 1:
            raise ValueError("invalid sequence")
        with self._db() as db:
            row = db.execute("""SELECT seq,information_id,revision,operation,canonical_sha256,state,created
                FROM intents WHERE seq=?""", (sequence,)).fetchone()
            return ChangeIntent(*row) if row else None
