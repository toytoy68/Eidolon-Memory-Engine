# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/indexing/orphan_scan.py
# Description : Resumable inverse inventory with revalidated orphan review.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Read-only index/journal/canon observations, persisted in a private checkpoint.

No deletion or DELETE intent is produced. EXHAUSTED means the scroll ended,
not that a live index was frozen or all concurrent inserts were seen. Explicit
restart begins another pass; review_page rechecks every saved observation.
All canonical, rights and alias writers must respect external coordination.
Returned candidates are for human review, never executable deletion permits.
"""
from contextlib import closing, contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sqlite3
import stat
import time
from uuid import UUID

from core.persistence import exclusive_write, has_symlink_component, RepositoryBusy
from .change_journal import ChangeJournal
from .port import IndexEvidence, IndexInventoryPage, IndexRecord
from .worker_canonical import CanonicalReader


@dataclass(frozen=True)
class OrphanReport:
    state: str
    inspected: int = 0
    observed_candidates: int = 0
    review_count: int = 0


@dataclass(frozen=True)
class OrphanObservation:
    position: int
    information_id: str
    state: str
    evidence: IndexEvidence | None
    checked_at: float


@dataclass(frozen=True)
class OrphanReview:
    state: str
    items: tuple[OrphanObservation, ...] = ()
    next_after: int | None = None


class _IndexUnavailable(Exception):
    pass


class OrphanScan:
    def __init__(self, checkpoint, journal, *, canonical_root, index, authorize,
                 profile_id, expected_profile_id, expected_model_id, max_points=100000):
        if (not isinstance(journal, ChangeJournal) or not callable(authorize)
                or any(type(v) is not str or not v for v in
                       (profile_id, expected_profile_id, expected_model_id, getattr(index, "alias", None)))
                or any(not callable(getattr(index, method, None)) for method in
                       ("active_generation", "inventory_page", "evidence_for"))
                or type(max_points) is not int or max_points < 1):
            raise ValueError("invalid orphan scan configuration")
        self.reader = CanonicalReader(canonical_root)
        self.journal, self.index, self.authorize = journal, index, authorize
        self.profile_id, self.expected_profile_id = profile_id, expected_profile_id
        self.expected_model_id, self.max_points = expected_model_id, max_points
        self.path = Path(checkpoint).absolute()
        if (has_symlink_component(self.path) or not self.path.parent.is_dir()
                or stat.S_IMODE(self.path.parent.stat().st_mode) & 0o077):
            raise ValueError("checkpoint requires a private directory without links")
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, 0o600)
        try:
            info = os.fstat(fd)
            journal_info = Path(journal.path).stat()
            if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077
                    or (info.st_dev, info.st_ino) == (journal_info.st_dev, journal_info.st_ino)):
                raise ValueError("checkpoint requires a separate private regular file")
        finally:
            os.close(fd)
        with self._db() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone():
                    raise ValueError("unrecognized orphan checkpoint")
                db.execute("""CREATE TABLE orphan_scan (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1), context TEXT NOT NULL,
                    generation TEXT NOT NULL, offset TEXT, phase TEXT NOT NULL CHECK(phase IN
                    ('RUNNING','EXHAUSTED','RESTART_REQUIRED')), seen INTEGER NOT NULL CHECK(seen>=0))""")
                db.execute("""CREATE TABLE observations (
                    position INTEGER PRIMARY KEY CHECK(position>=0), identity TEXT NOT NULL UNIQUE,
                    revision INTEGER NOT NULL CHECK(revision>0), digest TEXT, result TEXT NOT NULL,
                    observed REAL NOT NULL)""")
                db.execute("PRAGMA user_version=1")
            elif version != 1:
                raise ValueError("unsupported orphan checkpoint version")
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='orphan_scan' AND type='table'").fetchone():
                raise ValueError("not an orphan checkpoint")

    @contextmanager
    def _db(self):
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            db.execute("PRAGMA synchronous=FULL")
            with db:
                db.execute("BEGIN IMMEDIATE")
                yield db

    def _context(self):
        root, journal = self.reader.root.stat(), Path(self.journal.path).stat()
        if (root.st_dev, root.st_ino) != self.reader._root_identity:
            raise ValueError("canonical root changed")
        return json.dumps(dict(root=str(self.reader.root), root_identity=[root.st_dev, root.st_ino],
                               journal=str(Path(self.journal.path).absolute()),
                               journal_identity=[journal.st_dev, journal.st_ino], alias=self.index.alias,
                               model=self.expected_model_id, profile=self.profile_id,
                               expected_profile=self.expected_profile_id), sort_keys=True)

    def _load(self, db):
        row = db.execute("SELECT context,generation,offset,phase,seen FROM orphan_scan WHERE singleton=1").fetchone()
        count, low, high = db.execute("SELECT count(*),min(position),max(position) FROM observations").fetchone()
        if row is None:
            if count:
                raise ValueError("observations without scan")
            return None
        if row[0] != self._context():
            raise ValueError("checkpoint context differs; use a separate checkpoint")
        if (count != row[4] or (count and (low != 0 or high != count - 1))
                or (row[3] == "EXHAUSTED" and row[2] is not None)
                or (row[3] == "RUNNING" and count and row[2] is None)):
            raise ValueError("incomplete orphan checkpoint")
        if row[2] is not None and (type(row[2]) is not str or str(UUID(row[2])) != row[2]):
            raise ValueError("invalid checkpoint cursor")
        return row

    def _index_call(self, method, *args, **kwargs):
        try:
            return getattr(self.index, method)(*args, **kwargs)
        except Exception as exc:
            raise _IndexUnavailable from exc

    def _generation(self):
        value = self._index_call("active_generation")
        if type(value) is not str or not value:
            raise _IndexUnavailable("invalid generation")
        return value

    def _allowed(self, ident):
        return (self.profile_id == self.expected_profile_id
                and self.authorize(self.profile_id, ident, "index.delete") is True)

    def _observe(self, record, generation):
        ident = record.information_id
        if not self._allowed(ident):
            return "FORBIDDEN"
        if record.evidence is None:
            return "PROVENANCE_MISSING"
        if self.journal.has_pending(ident):
            return "PENDING_JOURNAL"
        try:
            if not self.reader.proven_absent(ident):
                return "CANONICAL_PRESENT"
        except (ValueError, OSError):
            return "ABSENCE_UNKNOWN"
        if self._index_call("evidence_for", ident) != record.evidence:
            return "POINT_CHANGED"
        if not self._allowed(ident):
            return "FORBIDDEN"
        if self._generation() != generation:
            raise _IndexUnavailable("generation changed")
        try:
            if not self.reader.proven_absent(ident):
                return "CANONICAL_PRESENT"
        except (ValueError, OSError):
            return "ABSENCE_UNKNOWN"
        return "PENDING_JOURNAL" if self.journal.has_pending(ident) else "DELETE_CANDIDATE"

    @staticmethod
    def _report(db, state=None):
        row = db.execute("SELECT phase,seen FROM orphan_scan WHERE singleton=1").fetchone()
        count = db.execute("SELECT count(*) FROM observations WHERE result='DELETE_CANDIDATE'").fetchone()[0]
        review = db.execute("SELECT count(*) FROM observations WHERE result!='CANONICAL_PRESENT'").fetchone()[0]
        return OrphanReport(state or row[0], row[1], count, review) if row else OrphanReport(state or "RUNNING")

    def run_page(self, *, limit=100, restart=False):
        """Atomically persist one observed page and its cursor, or retry it whole."""
        if type(limit) is not int or not 1 <= limit <= 999 or type(restart) is not bool:
            raise ValueError("invalid page options")
        try:
            with exclusive_write(self.reader.root, blocking=False), self._db() as db:
                row = self._load(db)
                if getattr(self.index, "embedding_id", None) != self.expected_model_id:
                    return self._report(db, "INDEX_INCOMPATIBLE")
                try:
                    generation = self._generation()
                    if row and row[1] != generation and not restart and row[3] != "RESTART_REQUIRED":
                        db.execute("UPDATE orphan_scan SET phase='RESTART_REQUIRED'")
                        return self._report(db)
                    if row is None or restart or row[3] == "RESTART_REQUIRED":
                        db.execute("DELETE FROM observations")
                        db.execute("INSERT OR REPLACE INTO orphan_scan VALUES (1,?,?,NULL,'RUNNING',0)",
                                   (self._context(), generation))
                        row = self._load(db)
                    if row[3] == "EXHAUSTED":
                        return self._report(db)
                    page = self._index_call("inventory_page", generation=generation, offset=row[2], limit=limit)
                    if type(page) is not IndexInventoryPage or page.generation != generation:
                        raise _IndexUnavailable("invalid inventory page")
                    if row[4] + len(page.records) > self.max_points:
                        return self._report(db, "LIMIT_REACHED")
                    observed = []
                    for i, record in enumerate(page.records, row[4]):
                        result = self._observe(record, generation)
                        observed.append((i, record.information_id, record.revision,
                                         record.evidence.canonical_sha256 if record.evidence else None,
                                         result, time.time()))
                    if self._generation() != generation:
                        raise _IndexUnavailable("generation changed")
                    db.executemany("INSERT INTO observations VALUES (?,?,?,?,?,?)", observed)
                    db.execute("UPDATE orphan_scan SET offset=?,phase=?,seen=?",
                               (page.next_offset, "EXHAUSTED" if page.next_offset is None else "RUNNING",
                                row[4] + len(observed)))
                    return self._report(db)
                except _IndexUnavailable:
                    return self._report(db, "INDEX_UNAVAILABLE")
        except RepositoryBusy:
            return OrphanReport("BUSY")

    def review_page(self, *, after=-1, limit=100):
        """Re-read observations in stable position order; never trusts stored verdicts.

        Candidates remain point-in-time observations. A future executor must
        independently recheck authority, absence, journal and exact point proof.
        """
        if type(after) is not int or after < -1 or type(limit) is not int or not 1 <= limit <= 999:
            raise ValueError("invalid review options")
        try:
            with exclusive_write(self.reader.root, blocking=False), self._db() as db:
                row = self._load(db)
                if row is None:
                    return OrphanReview("NOT_STARTED")
                if getattr(self.index, "embedding_id", None) != self.expected_model_id:
                    return OrphanReview("INDEX_INCOMPATIBLE")
                try:
                    if row[3] == "RESTART_REQUIRED" or self._generation() != row[1]:
                        return OrphanReview("RESTART_REQUIRED")
                    entries = db.execute("""SELECT position,identity,revision,digest FROM observations
                        WHERE position>? ORDER BY position LIMIT ?""", (after, limit + 1)).fetchall()
                    items = []
                    for position, ident, revision, digest in entries[:limit]:
                        evidence = IndexEvidence(ident, revision, digest, self.expected_model_id, row[1]) if digest else None
                        state = self._observe(IndexRecord(ident, revision, evidence), row[1])
                        items.append(OrphanObservation(position, ident, state, evidence, time.time()))
                    if self._generation() != row[1]:
                        return OrphanReview("RESTART_REQUIRED")
                    return OrphanReview("REVIEW", tuple(items), items[-1].position if len(entries) > limit else None)
                except _IndexUnavailable:
                    return OrphanReview("INDEX_UNAVAILABLE")
        except RepositoryBusy:
            return OrphanReview("BUSY")
