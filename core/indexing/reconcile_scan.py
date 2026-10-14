# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/indexing/reconcile_scan.py
# Description : Durable canonical scan recovering missing journal upserts.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Explicit, bounded canonical-to-journal reconciliation; never writes Qdrant.

Pages resume from a private SQLite checkpoint. Complete canonical snapshots at
start/end detect edits behind the cursor. They hold the writer lock and have
entry/byte budgets; exceeding a budget fails, never certifies a partial scan.
Continuous canonical edits can force repeated passes. COMPLETE describes the
canonical pass, not a synchronized index or a durable permission/alias lease.
"""
from contextlib import closing, contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sqlite3
import stat

from core.persistence import exclusive_write, has_symlink_component, RepositoryBusy
from .change_journal import ChangeJournal, JournalCapacityExceeded
from .port import IndexEvidence
from .worker_canonical import CanonicalReader


@dataclass(frozen=True)
class ScanReport:
    state: str
    cursor: int = 0
    total: int = 0
    review_count: int = 0
    queued: tuple[int, ...] = ()


class _IndexUnavailable(Exception):
    pass


class ReconciliationScan:
    def __init__(self, checkpoint, journal, *, canonical_root, index, authorize,
                 profile_id, expected_profile_id, expected_model_id,
                 max_entries=100000, max_file_bytes=8 * 1024 * 1024,
                 max_total_bytes=256 * 1024 * 1024, pending_limit=100):
        if (not isinstance(journal, ChangeJournal) or not callable(authorize)
                or any(type(s) is not str or not s for s in
                       (profile_id, expected_profile_id, expected_model_id, getattr(index, "alias", None)))
                or not callable(getattr(index, "evidence_for", None))
                or not callable(getattr(index, "active_generation", None))
                or any(type(n) is not int or n < 1 for n in (max_entries, max_file_bytes, max_total_bytes))
                or type(pending_limit) is not int or not 1 <= pending_limit <= 999):
            raise ValueError("invalid reconciliation configuration")
        self.reader = CanonicalReader(canonical_root, max_bytes=max_file_bytes)
        self.journal, self.index, self.authorize = journal, index, authorize
        self.profile_id, self.expected_profile_id = profile_id, expected_profile_id
        self.expected_model_id = expected_model_id
        self.max_entries, self.max_total_bytes = max_entries, max_total_bytes
        self.pending_limit = pending_limit
        self.path = Path(checkpoint).absolute()
        if (self.path == Path(journal.path).absolute() or has_symlink_component(self.path)
                or not self.path.parent.is_dir()
                or stat.S_IMODE(self.path.parent.stat().st_mode) & 0o077):
            raise ValueError("checkpoint requires a separate private regular file")
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
                raise ValueError("checkpoint must be private and regular")
        finally:
            os.close(fd)
        with self._db() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone():
                    raise ValueError("unrecognized checkpoint")
                db.execute("""CREATE TABLE scan (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1), context TEXT NOT NULL,
                    generation TEXT NOT NULL, phase TEXT NOT NULL CHECK(phase IN
                    ('RUNNING','VERIFYING','COMPLETE','REVIEW_REQUIRED','RESTART_REQUIRED')),
                    cursor INTEGER NOT NULL CHECK(cursor>=0), total INTEGER NOT NULL CHECK(total>=cursor))""")
                db.execute("""CREATE TABLE entries (
                    position INTEGER PRIMARY KEY CHECK(position>=0), identity TEXT NOT NULL UNIQUE,
                    revision INTEGER NOT NULL CHECK(revision>0), digest TEXT NOT NULL,
                    result TEXT, sequence INTEGER)""")
                db.execute("PRAGMA user_version=1")
            elif version != 1:
                raise ValueError("unsupported checkpoint version")

    @contextmanager
    def _db(self):
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            db.execute("PRAGMA synchronous=FULL")
            with db:
                db.execute("BEGIN IMMEDIATE")
                yield db

    def _context(self):
        root = self.reader.root.stat()
        if (root.st_dev, root.st_ino) != self.reader._root_identity:
            raise ValueError("canonical root changed")
        journal = Path(self.journal.path).absolute()
        info = journal.stat()
        return json.dumps(dict(root=str(self.reader.root), root_identity=[root.st_dev, root.st_ino],
                               journal=str(journal), journal_identity=[info.st_dev, info.st_ino],
                               alias=self.index.alias, model=self.expected_model_id,
                               profile=self.profile_id, expected_profile=self.expected_profile_id), sort_keys=True)

    def _index_call(self, method, *args):
        try:
            return getattr(self.index, method)(*args)
        except Exception as exc:
            raise _IndexUnavailable from exc

    def _snapshot(self):
        entries, consumed = [], 0
        for ident in self.reader.information_ids(max_entries=self.max_entries):
            memory, digest, size = self.reader.read_sized(ident)
            consumed += size
            if consumed > self.max_total_bytes:
                raise ValueError("canonical snapshot exceeds total byte limit")
            entries.append((ident, memory.revision, digest))
        return entries

    def _load(self, db, context):
        row = db.execute("SELECT context,generation,phase,cursor,total FROM scan WHERE singleton=1").fetchone()
        if row is None:
            if db.execute("SELECT 1 FROM entries LIMIT 1").fetchone():
                raise ValueError("checkpoint entries without scan")
            return None
        if row[0] != context:
            raise ValueError("checkpoint context differs; use a separate checkpoint")
        count, low, high = db.execute("SELECT count(*),min(position),max(position) FROM entries").fetchone()
        if (count != row[4] or (count and (low != 0 or high != count - 1))
                or (row[2] in ("VERIFYING", "COMPLETE", "REVIEW_REQUIRED") and row[3] != row[4])
                or db.execute("SELECT 1 FROM entries WHERE position<? AND result IS NULL LIMIT 1",
                              (row[3],)).fetchone()):
            raise ValueError("incomplete checkpoint")
        return row

    def _report(self, db, state=None, queued=()):
        row = db.execute("SELECT phase,cursor,total FROM scan WHERE singleton=1").fetchone()
        count = db.execute("SELECT count(*) FROM entries WHERE result IS NOT NULL AND result NOT IN ('VERIFIED','QUEUED')").fetchone()[0]
        return ScanReport(state or row[0], row[1], row[2], count, tuple(queued)) if row else ScanReport(state or "RUNNING")

    def run_page(self, *, limit=100, restart=False):
        """Process one page, or verify the final complete canonical snapshot.

        Completed checkpoints are inert until restart=True requests a new pass.
        RESTART_REQUIRED restarts automatically on the next explicit call.
        Journal commits precede checkpoint progress: retries deduplicate intents.
        """
        if type(limit) is not int or not 1 <= limit <= 999 or type(restart) is not bool:
            raise ValueError("invalid page options")
        try:
            with exclusive_write(self.reader.root, blocking=False), self._db() as db:
                context = self._context()
                row = self._load(db, context)
                if getattr(self.index, "embedding_id", None) != self.expected_model_id:
                    return self._report(db, "INDEX_INCOMPATIBLE")
                queued = []
                try:
                    generation = self._index_call("active_generation")
                    if type(generation) is not str or not generation:
                        raise ValueError("invalid generation")
                    if row is not None and not restart and row[2] in ("COMPLETE", "REVIEW_REQUIRED"):
                        return self._report(db)
                    if row is None or restart or row[2] == "RESTART_REQUIRED":
                        snapshot = self._snapshot()
                        if self._index_call("active_generation") != generation:
                            return self._report(db, "INDEX_UNAVAILABLE")
                        db.execute("DELETE FROM entries")
                        db.executemany("INSERT INTO entries(position,identity,revision,digest) VALUES (?,?,?,?)",
                                       [(pos, *entry) for pos, entry in enumerate(snapshot)])
                        db.execute("INSERT OR REPLACE INTO scan VALUES (1,?,?,'RUNNING',0,?)",
                                   (context, generation, len(snapshot)))
                        row = self._load(db, context)
                    if row[1] != generation:
                        db.execute("UPDATE scan SET phase='RESTART_REQUIRED'")
                        return self._report(db)
                    if row[2] == "VERIFYING":
                        current = self._snapshot()
                        saved = db.execute("SELECT identity,revision,digest FROM entries ORDER BY position").fetchall()
                        if current != saved or self._index_call("active_generation") != generation:
                            phase = "RESTART_REQUIRED"
                        else:
                            phase = "REVIEW_REQUIRED" if self._report(db).review_count else "COMPLETE"
                        db.execute("UPDATE scan SET phase=?", (phase,))
                        return self._report(db)
                    page = db.execute("""SELECT position,identity,revision,digest FROM entries
                                         WHERE position>=? ORDER BY position LIMIT ?""", (row[3], limit)).fetchall()
                    for position, ident, revision, digest in page:
                        result, seq = self._inspect(ident, revision, digest, generation)
                        if result == "RESTART_REQUIRED":
                            db.execute("UPDATE scan SET phase='RESTART_REQUIRED'")
                            return self._report(db, queued=queued)
                        db.execute("UPDATE entries SET result=?,sequence=? WHERE position=?", (result, seq, position))
                        db.execute("UPDATE scan SET cursor=?", (position + 1,))
                        if seq is not None:
                            queued.append(seq)
                    db.execute("UPDATE scan SET phase='VERIFYING' WHERE cursor=total")
                    return self._report(db, queued=queued)
                except _IndexUnavailable:
                    # Commit already processed entries, retry the uncertain one.
                    return self._report(db, "INDEX_UNAVAILABLE", queued)
                except JournalCapacityExceeded:
                    return self._report(db, "JOURNAL_FULL", queued)
        except RepositoryBusy:
            return ScanReport("BUSY")

    def _allowed(self, ident):
        return (self.profile_id == self.expected_profile_id
                and self.authorize(self.profile_id, ident, "index.upsert") is True)

    def _inspect(self, ident, revision, digest, generation):
        if not self._allowed(ident):
            return "FORBIDDEN", None
        try:
            memory, current_digest = self.reader(ident)
        except (ValueError, OSError, UnicodeError):
            return "RESTART_REQUIRED", None
        if (memory.revision, current_digest) != (revision, digest):
            return "RESTART_REQUIRED", None
        point = self._index_call("evidence_for", ident)
        if point is not None:
            if (type(point) is not IndexEvidence or point.information_id != ident
                    or type(point.revision) is not int or point.revision < 1
                    or type(point.canonical_sha256) is not str
                    or re.fullmatch(r"[0-9a-f]{64}", point.canonical_sha256) is None
                    or point.embedding_id != self.expected_model_id or point.generation != generation
                    or point.revision > revision
                    or (point.revision == revision and point.canonical_sha256 != digest)):
                return "INDEX_CONFLICT", None
        if not self._allowed(ident):
            return "FORBIDDEN", None
        # Flush only when recovering a lost event; existing verified points need
        # no journal transition. Canonical content is always checked again.
        matching = point is not None and point.revision == revision
        read = self.reader if matching else self.reader.read_durable
        try:
            memory, current_digest = read(ident)
        except (ValueError, OSError, UnicodeError):
            return "RESTART_REQUIRED", None
        if ((memory.revision, current_digest) != (revision, digest)
                or self._index_call("active_generation") != generation):
            return "RESTART_REQUIRED", None
        if matching:
            return "VERIFIED", None
        seq = self.journal.ensure_upsert_intent(ident, revision, digest, pending_limit=self.pending_limit)
        return ("QUEUED", seq) if seq is not None else ("JOURNAL_CONFLICT", None)

    def issues(self, *, limit=100):
        """Read bounded durable review reasons, without interpreting them as actions."""
        if type(limit) is not int or not 1 <= limit <= 999:
            raise ValueError("invalid issue limit")
        with self._db() as db:
            self._load(db, self._context())
            return tuple(db.execute("""SELECT identity,result FROM entries WHERE result IS NOT NULL
                AND result NOT IN ('VERIFIED','QUEUED') ORDER BY position LIMIT ?""", (limit,)).fetchall())
