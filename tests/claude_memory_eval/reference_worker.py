# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/reference_worker.py
# Description : Worker de référence Claude (G214-3) pour la recette isolée : planifier, revérifier, agir
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""TEST REFERENCE ONLY (Claude, G214-3), not a production worker: it fixes the CONTRACT that GPT's worker
must pass, with in-memory doubles. Three stages:

1. plan    : preview_reconciliation on a canonical snapshot (Canonical, ABSENT or missing = unknown);
2. verify  : for every action, re-read the canon NOW and check the profile's rights;
3. act     : journal transitions and index upserts only after verification.

Never: a Qdrant deletion (deletions are PROPOSED for review), an abandonment without review, an index write
when the canon cannot be read, ``indexed()`` before the index read-back.
"""
import fcntl
import os
from dataclasses import dataclass, field

from core.indexing.reconcile_plan import ABSENT
from core.indexing.reconcile_preview import preview_reconciliation
from core.indexing.worker_preflight import preflight


from core.indexing.worker import Crash, IndexUnavailable, CanonUnreadable


@dataclass
class Report:
    status: str = "DONE"
    applied: list = field(default_factory=list)
    review: list = field(default_factory=list)
    proposed_deletions: list = field(default_factory=list)
    skipped: list = field(default_factory=list)


class ReferenceWorker:
    def __init__(self, journal, canon, index, rights, *, profile, lock_path, clock, grace_seconds=600,
                 crash_at=None, hooks=None, descriptor=("embed-test/1", "passage-v1")):
        self.journal, self.canon, self.index, self.rights = journal, canon, index, rights
        self.profile, self.lock_path, self.clock = profile, lock_path, clock
        self.grace_seconds, self.crash_at, self.hooks = grace_seconds, crash_at, hooks or {}
        self.descriptor = descriptor                               # (embedding_id, chunker version) expected

    def _point(self, name):
        if name in self.hooks:
            self.hooks[name]()
        if self.crash_at == name:
            raise Crash(name)

    def run_once(self):
        fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return Report("BUSY")
            return self._run()
        finally:
            os.close(fd)

    def _run(self):
        report = Report()
        try:
            if self.index.descriptor() != self.descriptor:
                return Report("INDEX_INCOMPATIBLE")                 # model or chunker changed: full rebuild
            indexed = self.index.revisions()
        except IndexUnavailable:
            return Report("INDEX_UNAVAILABLE")
        ids = set(indexed) | {i.information_id for i in self.journal.pending(limit=999)} | self.canon.listing()
        snapshot = self.canon.snapshot(ids)                          # unreadable ids are simply missing
        try:
            preview = preview_reconciliation(self.journal, snapshot, indexed, now=self.clock(),
                                             grace_seconds=self.grace_seconds, limit=999)
        except ValueError as exc:                                    # truncated journal, clock behind intents
            return Report("TRUNCATED" if "truncated" in str(exc) else "REFUSED")
        self._point("after_plan")
        gate = preflight([a for a in preview.actions if a.kind != "WAIT"], allow_upsert=True)   # GPT, 1a7a76f
        executable = {id(a) for a in gate.proposals}
        for action in preview.actions:
            if action.kind == "WAIT":
                report.skipped.append((action.information_id, "wait"))
                continue
            if action.kind == "MARK_PUBLISHED":
                # Journal recovery is a distinct privileged transition, never
                # an index operation. Re-read and compare the canonical snapshot.
                try:
                    current = self.canon.read(action.information_id)
                except CanonUnreadable:
                    report.skipped.append((action.information_id, "canon unreadable"))
                    continue
                if (current != snapshot.get(action.information_id)
                        or current is ABSENT and action.revision is None):
                    report.skipped.append((action.information_id, "canon changed since plan"))
                    continue
                if self.rights(self.profile, action.information_id) is not True:
                    report.skipped.append((action.information_id, "forbidden"))
                    continue
                self.journal.published(action.sequence)
                report.applied.append((action.kind, action.information_id, action.sequence))
                continue
            deletion = action.kind in ("INDEX_DELETE", "ENQUEUE_DELETE")
            if id(action) not in executable and not deletion:
                report.review.append((action.kind, action.information_id, action.sequence))
                continue
            try:
                current = self.canon.read(action.information_id)          # stage 2: re-read NOW
            except CanonUnreadable:
                report.skipped.append((action.information_id, "canon unreadable"))
                continue
            if not self.rights(self.profile, action.information_id):
                report.skipped.append((action.information_id, "forbidden"))
                continue
            if deletion:                                             # verified, then only PROPOSED
                if current is ABSENT:
                    report.proposed_deletions.append((action.information_id, action.sequence))
                else:
                    report.skipped.append((action.information_id, "absence not confirmed"))
                continue
            try:
                self._act(action, current, report)
            except IndexUnavailable:
                report.status = "INDEX_UNAVAILABLE"
                return report
        return report

    def _act(self, action, current, report):
        ident, seq = action.information_id, action.sequence
        if action.kind == "MARK_PUBLISHED":
            self.journal.published(seq)
        elif action.kind in ("INDEX_UPSERT", "ENQUEUE_UPSERT"):
            if current is ABSENT or current.revision != action.revision:
                report.skipped.append((ident, "canon changed since plan"))
                return
            self._point("before_upsert")                             # embeddings are computed here
            self.index.upsert(ident, current.revision, current.sha256)
            self._point("after_upsert")
            if self.index.revisions().get(ident) != current.revision:       # read-back before indexed()
                report.skipped.append((ident, "index read-back failed"))
                return
            try:
                still = self.canon.read(ident)
            except CanonUnreadable:
                still = None
            if still != current:                                     # canon moved while indexing
                report.skipped.append((ident, "canon changed while indexing"))
                return
            if seq is not None:
                self.journal.indexed(seq)
        else:
            raise ValueError(f"unexpected action {action.kind}")
        report.applied.append((action.kind, ident, seq))


class FakeCanon:
    """Canonical Markdown double: {id: Canonical}; ``unreadable`` ids raise on read."""

    def __init__(self):
        self.docs, self.unreadable = {}, set()

    def listing(self):
        return set(self.docs) - self.unreadable

    def read(self, ident):
        if ident in self.unreadable:
            raise CanonUnreadable(ident)
        return self.docs.get(ident, ABSENT)

    def snapshot(self, ids):
        return {ident: self.docs.get(ident, ABSENT) for ident in ids if ident not in self.unreadable}


class FakeIndex:
    """Qdrant double: deterministic point per id; counts effective writes; never deletes."""

    def __init__(self):
        self.points, self.writes, self.available = {}, 0, True
        self.model, self.lose_next_ack = ("embed-test/1", "passage-v1"), False

    def descriptor(self):
        if not self.available:
            raise IndexUnavailable()
        return self.model

    def revisions(self):
        if not self.available:
            raise IndexUnavailable()
        return {ident: point[0] for ident, point in self.points.items()}

    def upsert(self, ident, revision, sha256):
        if not self.available:
            raise IndexUnavailable()
        if self.points.get(ident) != (revision, sha256):
            self.writes += 1
        self.points[ident] = (revision, sha256)
        if self.lose_next_ack:                                       # written, but the caller never knows
            self.lose_next_ack = False
            raise IndexUnavailable("ack lost")