# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/indexing/worker_journal.py
# Description : Bounded journal upserts with canonical and point verification.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Opt-in journal consumer; no daemon, deletion, abandonment or manifest scan.

Every canonical writer must share the persistent-root lock. Policy and alias
writers must also cooperate while this worker runs. Cross-service atomicity is
not claimed: an interrupted/uncertain effect stays pending for fresh read-back.
The index and journal are trusted private adapters, never caller-supplied data.
"""
from dataclasses import dataclass
import math
import time

from core.persistence import exclusive_write, RepositoryBusy
from core.backend.errors import InvalidMemory
from .change_journal import ChangeJournal
from .port import IndexEvidence, IndexIncompatible
from .reconcile_plan import Action
from .worker_canonical import CanonicalReader
from .worker_upsert import apply_upsert


@dataclass(frozen=True)
class JournalReport:
    status: str = "DONE"
    published: tuple[int, ...] = ()
    indexed: tuple[int, ...] = ()
    deferred: tuple[tuple[int, str], ...] = ()


@dataclass(frozen=True)
class JournalPageReport:
    status: str
    after: int
    through: int | None
    exhausted: bool
    result: JournalReport


class _IndexUnavailable(Exception):
    pass


class _GuardedIndex:
    """Separate adapter failures from journal/policy/reader programming errors."""
    def __init__(self, index):
        self.index = index
        self.embedding_id = index.embedding_id

    def evidence_for(self, ident):
        try:
            return self.index.evidence_for(ident)
        except IndexIncompatible:
            raise
        except Exception as exc:
            raise _IndexUnavailable from exc

    def upsert_verified(self, memory, *, canonical_sha256):
        try:
            return self.index.upsert_verified(memory, canonical_sha256=canonical_sha256)
        except IndexIncompatible:
            raise
        except Exception as exc:
            raise _IndexUnavailable from exc


class JournalUpsertWorker:
    def __init__(self, journal, *, canonical_root, index, authorize,
                 profile_id, expected_profile_id, expected_model_id):
        if (not isinstance(journal, ChangeJournal) or not callable(authorize)
                or any(type(s) is not str or not s for s in
                       (profile_id, expected_profile_id, expected_model_id))
                or not callable(getattr(index, "active_generation", None))
                or not callable(getattr(index, "evidence_for", None))
                or not callable(getattr(index, "upsert_verified", None))):
            raise ValueError("invalid journal worker configuration")
        self.reader = CanonicalReader(canonical_root)
        self.journal, self.index, self.authorize = journal, index, authorize
        self.profile_id, self.expected_profile_id = profile_id, expected_profile_id
        self.expected_model_id = expected_model_id

    def _allowed(self, intent):
        return (self.profile_id == self.expected_profile_id
                and self.authorize(self.profile_id, intent.information_id, "index.upsert") is True)

    def _canonical(self, intent, *, durable=False):
        read = self.reader.read_durable if durable else self.reader
        memory, digest = read(intent.information_id)
        return memory.revision == intent.revision and digest == intent.canonical_sha256

    def _matches(self, point, intent):
        return (type(point) is IndexEvidence
                and point.information_id == intent.information_id
                and type(point.revision) is int and point.revision == intent.revision
                and point.canonical_sha256 == intent.canonical_sha256
                and point.embedding_id == self.expected_model_id
                and type(point.generation) is str and bool(point.generation))

    def run_once(self, *, limit=100, now=None):
        """Consume a complete bounded pending snapshot, under the writer lock.

        INTENT recovery is published only; indexing requires the next call.
        The caller must record the report and arrange explicit subsequent calls.
        Unknown/unsafe canonical reads never prove absence or authorize deletion.
        """
        if type(limit) is not int or not 1 <= limit <= 999:
            raise ValueError("invalid pending limit")
        try:
            with exclusive_write(self.reader.root, blocking=False):
                return self._run(limit, time.time() if now is None else now)
        except RepositoryBusy:
            return JournalReport("BUSY")

    def _run(self, limit, now):
        if type(now) not in (int, float) or not math.isfinite(now):
            raise ValueError("invalid clock")
        pending = self.journal.pending(limit + 1)
        if len(pending) > limit:
            return JournalReport("TRUNCATED")
        if any(type(i.created) not in (int, float) or not math.isfinite(i.created) or i.created > now for i in pending):
            return JournalReport("REFUSED")
        return self._process(pending, now)

    def run_page(self, *, after=0, through=None, limit=100, now=None):
        """One finite pass page. Caller persists cursor AFTER effects and replays safely.

        A reviewed row advances this pass; it remains pending for subsequent
        passes. An index outage keeps the failing row at the next cursor.
        Exhaustion is a pass boundary, never a declaration that the queue is empty.
        """
        if (type(after) is not int or after < 0
                or (through is not None and (type(through) is not int or through < after))
                or (through is None and after != 0)
                or type(limit) is not int or not 1 <= limit <= 999):
            raise ValueError("invalid worker page")
        now = time.time() if now is None else now
        if type(now) not in (int, float) or not math.isfinite(now):
            raise ValueError("invalid clock")
        try:
            with exclusive_write(self.reader.root, blocking=False):
                high = self.journal.high_watermark()
                fence = high if through is None else through
                if fence > high:
                    raise ValueError("worker pass exceeds journal high watermark")
                pending = self.journal.pending_page(after=after, through=fence, limit=limit+1)
                result = self._process(pending[:limit], now)
                visited = (*result.published, *result.indexed,
                           *(seq for seq, reason in result.deferred if reason not in ("INDEX_UNAVAILABLE", "INDEX_INCOMPATIBLE")))
                cursor = max((after, *visited))
                exhausted = result.status == "DONE" and len(pending) <= limit
                if exhausted:
                    cursor = fence
                status = ("PASS_EXHAUSTED" if exhausted else "MORE") if result.status == "DONE" else result.status
                return JournalPageReport(status, cursor, fence, exhausted, result)
        except RepositoryBusy:
            return JournalPageReport("BUSY", after, through, False,
                                     JournalReport("BUSY"))

    def _compatible_now(self):
        try:
            self.index.active_generation()
            return True
        except IndexIncompatible:
            raise
        except Exception as exc:
            raise _IndexUnavailable from exc

    def _process(self, pending, now):
        if getattr(self.index, "embedding_id", None) != self.expected_model_id:
            return JournalReport("INDEX_INCOMPATIBLE")
        try:
            self.index.active_generation()
        except IndexIncompatible:
            return JournalReport("INDEX_INCOMPATIBLE")
        except Exception:
            return JournalReport("INDEX_UNAVAILABLE")
        index = _GuardedIndex(self.index)
        published, indexed, deferred = [], [], []
        status = "DONE"
        for intent in pending:
            seq = intent.sequence
            if type(intent.created) not in (int, float) or not math.isfinite(intent.created) or intent.created > now:
                deferred.append((seq, "INVALID_TIMESTAMP"))
                continue
            if intent.operation != "UPSERT":
                deferred.append((seq, "DELETE_REQUIRES_REVIEW"))
                continue
            try:
                if not self._allowed(intent):
                    deferred.append((seq, "FORBIDDEN"))
                    continue
                memory, digest = self.reader(intent.information_id)
                if memory.revision > intent.revision:
                    deferred.append((seq, "SUPERSEDED_REQUIRES_REVIEW"))
                    continue
                if memory.revision != intent.revision or digest != intent.canonical_sha256:
                    deferred.append((seq, "CANONICAL_MISMATCH"))
                    continue
                if intent.state == "INTENT":
                    # Permission callbacks may change state: re-read after them.
                    if not self._allowed(intent) or not self._canonical(intent, durable=True):
                        deferred.append((seq, "STALE"))
                    elif self._compatible_now() and self.journal.advance_verified(intent, "PUBLISHED"):
                        published.append(seq)
                    else:
                        deferred.append((seq, "JOURNAL_CHANGED"))
                    continue
                point = index.evidence_for(intent.information_id)
                if point is not None and not self._matches(point, intent):
                    # An older revision is normal. Equal/newer conflicting evidence
                    # requires review rather than silently overwriting corruption.
                    if (type(point) is not IndexEvidence or type(point.revision) is not int
                            or point.revision >= intent.revision
                            or point.embedding_id != self.expected_model_id):
                        deferred.append((seq, "INDEX_CONFLICT"))
                        continue
                    point = None
                if point is None:
                    receipt = apply_upsert(
                        Action("INDEX_UPSERT", intent.information_id, seq, intent.revision, "journal"),
                        canonical_root=self.reader.root, read_canonical=self.reader,
                        authorize=self.authorize, index=index, profile_id=self.profile_id,
                        expected_profile_id=self.expected_profile_id,
                        model_id=self.expected_model_id, expected_model_id=self.expected_model_id,
                        expected_sha256=intent.canonical_sha256)
                    if receipt.state != "ACKNOWLEDGED":
                        deferred.append((seq, receipt.state))
                        continue
                    point = index.evidence_for(intent.information_id)
                # Also used after lost ack: verify again, without re-embedding.
                if (not self._matches(point, intent) or not self._allowed(intent)
                        or not self._canonical(intent)
                        or index.evidence_for(intent.information_id) != point):
                    deferred.append((seq, "STALE"))
                elif self.journal.advance_verified(intent, "INDEXED"):
                    indexed.append(seq)
                else:
                    deferred.append((seq, "JOURNAL_CHANGED"))
            except IndexIncompatible:
                deferred.append((seq, "INDEX_INCOMPATIBLE"))
                status = "INDEX_INCOMPATIBLE"
                break
            except _IndexUnavailable:
                deferred.append((seq, "INDEX_UNAVAILABLE"))
                status = "INDEX_UNAVAILABLE"
                break
            except (ValueError, OSError, UnicodeError, InvalidMemory):
                # No absent inference and no terminal transition on a bad read.
                deferred.append((seq, "UNVERIFIED"))
        return JournalReport(status, tuple(published), tuple(indexed), tuple(deferred))
