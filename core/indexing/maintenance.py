# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/indexing/maintenance.py
# Description : Durable bounded coordination of journal and canonical/index scans.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Explicit host-driven ticks; no thread, timer, daemon, model selection or delete.

The host supplies current activity/load/boot observations. Each eligible tick
performs at most one page (canonical start/end inventories retain G231 budgets).
Effects precede checkpoint progress and are replayed through their own guards.
Cycle completion describes observed work, not a distributed synchronization lease.
"""
from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, time, timezone
import json
import os
import re
from pathlib import Path
import sqlite3
import stat

from core.maintenance.window import preview_window, _instant
from core.persistence import exclusive_write, has_symlink_component, RepositoryBusy
from .port import IndexIncompatible
from .orphan_scan import OrphanScan
from .reconcile_scan import ReconciliationScan, CanonicalSnapshotUnavailable
from .worker_journal import JournalUpsertWorker
from .worker_port import WorkerIndexView


@dataclass(frozen=True)
class MaintenanceReport:
    state: str
    stage: str
    cycle: int
    next_at: float
    detail: dict


class IndexMaintenance:
    def __init__(self, checkpoint, journal, *, canonical_checkpoint, orphan_checkpoint,
                 canonical_root, index, authorize, profile_id, expected_profile_id,
                 expected_model_id, page_size=100, pending_limit=100, max_points=100000,
                 max_file_bytes=8 * 1024 * 1024,
                 retry_seconds=30, cycle_seconds=300, start=time(4), end=time(8),
                 zone="Europe/Paris", minimum_idle_minutes=30, minimum_boot_minutes=30):
        if (any(type(n) is not int or n < 1 for n in (max_points, max_file_bytes))
                or any(type(n) is not int or not 1 <= n <= 999 for n in (page_size, pending_limit))
                or any(type(n) is not int or n < 1 for n in
                       (retry_seconds, cycle_seconds, minimum_idle_minutes, minimum_boot_minutes))):
            raise ValueError("invalid maintenance budgets")
        self.path = Path(checkpoint).absolute()
        paths = [self.path, Path(canonical_checkpoint).absolute(), Path(orphan_checkpoint).absolute(),
                 Path(journal.path).absolute()]
        if len(set(paths)) != len(paths) or any(has_symlink_component(p) for p in paths):
            raise ValueError("maintenance requires separate files without links")
        identities = [(p.stat().st_dev, p.stat().st_ino) for p in paths if p.exists()]
        if len(set(identities)) != len(identities):
            raise ValueError("maintenance checkpoint files alias each other")
        index = index if isinstance(index, WorkerIndexView) else WorkerIndexView(index)
        self.journal, self.index = journal, index
        self.page_size, self.retry_seconds, self.cycle_seconds = page_size, retry_seconds, cycle_seconds
        self.window = dict(start=start, end=end, zone=zone, minimum_idle_minutes=minimum_idle_minutes)
        probe = datetime(2000, 1, 1, tzinfo=timezone.utc)
        preview_window(at=probe, last_activity=probe, **self.window)
        self.minimum_boot_minutes = minimum_boot_minutes
        common = dict(canonical_root=canonical_root, index=index, authorize=authorize,
                      profile_id=profile_id, expected_profile_id=expected_profile_id,
                      expected_model_id=expected_model_id)
        self.worker = JournalUpsertWorker(journal, max_file_bytes=max_file_bytes, **common)
        self.canonical = ReconciliationScan(paths[1], journal, pending_limit=pending_limit,
                                            max_file_bytes=max_file_bytes, **common)
        self.orphans = OrphanScan(paths[2], journal, max_points=max_points, **common)
        self.root = self.worker.reader.root
        self.context_options = dict(profile=profile_id, expected_profile=expected_profile_id,
            model=expected_model_id, alias=index.alias, page_size=page_size, pending_limit=pending_limit,
            retry_seconds=retry_seconds, cycle_seconds=cycle_seconds, start=start.isoformat(),
            end=end.isoformat(), zone=zone, minimum_idle_minutes=minimum_idle_minutes,
            minimum_boot_minutes=minimum_boot_minutes)
        # Omit the historical default so v1 checkpoints retain their exact context.
        if max_points != 100000:
            self.context_options["max_points"] = max_points
        if max_file_bytes != 8 * 1024 * 1024:
            self.context_options["max_file_bytes"] = max_file_bytes
        self.bound_paths = [self.root, *paths[1:]]
        if not self.path.parent.is_dir() or stat.S_IMODE(self.path.parent.stat().st_mode) & 0o077:
            raise ValueError("maintenance checkpoint requires a private directory")
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
                raise ValueError("maintenance checkpoint must be private and regular")
        finally:
            os.close(fd)
        with self._db() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone():
                    raise ValueError("unrecognized maintenance checkpoint")
                db.execute("CREATE TABLE maintenance (singleton INTEGER PRIMARY KEY CHECK(singleton=1), context TEXT NOT NULL, state TEXT NOT NULL)")
                db.execute("CREATE TABLE reviews (sequence INTEGER PRIMARY KEY, reason TEXT NOT NULL, observed REAL NOT NULL)")
                db.execute("INSERT INTO maintenance VALUES (1,?,?)", (self._context(), json.dumps(self._new(1))))
                version = 1
            elif version not in (1, 2):
                raise ValueError("unsupported maintenance checkpoint")
            self._load(db)
            if version == 1:
                db.execute("CREATE TABLE clock_fault (singleton INTEGER PRIMARY KEY CHECK(singleton=1), observed_at REAL NOT NULL)")
                db.execute("CREATE TABLE clock_recoveries (sequence INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT NOT NULL UNIQUE, receipt TEXT NOT NULL)")
                db.execute("PRAGMA user_version=2")

    @staticmethod
    def _new(cycle):
        return dict(stage="FIRST", cycle=cycle, after=0, through=None, generation=None, next_at=0., last_at=0.,
                    outcome="ACTIVE", canonical_done=False, orphan_done=False,
                    canonical_restart=True, orphan_restart=True, canonical_blocked=False,
                    canonical_review=0, orphan_review=0, progress=0, last_result={})

    @contextmanager
    def _db(self):
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            db.execute("PRAGMA synchronous=FULL")
            with db:
                db.execute("BEGIN IMMEDIATE")
                yield db

    def _context(self):
        def identity(p):
            if has_symlink_component(p):
                raise ValueError("maintenance context contains a link")
            info = p.stat()
            return [str(p), info.st_dev, info.st_ino]
        return json.dumps(dict(paths=[identity(p) for p in self.bound_paths], **self.context_options), sort_keys=True)

    def _load(self, db):
        row = db.execute("SELECT context,state FROM maintenance WHERE singleton=1").fetchone()
        if row is None or row[0] != self._context():
            raise ValueError("maintenance context differs; use separate checkpoints")
        s = json.loads(row[1])
        template = self._new(1)
        if (type(s) is not dict or s.keys() != template.keys()
                or s["stage"] not in ("FIRST", "SECOND", "CANONICAL", "ORPHANS", "FINISH")
                or s["outcome"] not in ("ACTIVE", "CYCLE_COMPLETE", "REVIEW_REQUIRED")
                or (s["generation"] is not None and (type(s["generation"]) is not str or not s["generation"]))
                or any(type(s[k]) is not bool for k in ("canonical_done", "orphan_done", "canonical_restart", "orphan_restart", "canonical_blocked"))
                or any(type(s[k]) is not int or s[k] < 0 for k in ("after", "canonical_review", "orphan_review", "progress"))
                or type(s["cycle"]) is not int or s["cycle"] < 1
                or (s["through"] is not None and (type(s["through"]) is not int or s["through"] < s["after"]))
                or (s["through"] is None and s["after"] != 0)
                or any(type(s[k]) not in (int, float) or not 0 <= s[k] < float("inf") for k in ("last_at", "next_at"))
                or (s["outcome"] != "ACTIVE" and s["stage"] != "FINISH")
                or (s["outcome"] == "CYCLE_COMPLETE" and
                    (not s["canonical_done"] or not s["orphan_done"] or s["canonical_review"] or s["orphan_review"]))):
            raise ValueError("invalid maintenance state")
        return s

    def _save(self, db, s):
        db.execute("UPDATE maintenance SET state=? WHERE singleton=1", (json.dumps(s, allow_nan=False),))

    @staticmethod
    def _report(s, state, detail=None):
        return MaintenanceReport(state, s["stage"], s["cycle"], s["next_at"], detail or {})

    def tick(self, *, at, last_activity, boot_at, load_ok):
        """Evaluate live host observations, then perform at most one durable step.

        All supplied times must be aware. Unknown/high load defers. Window and
        idle checks do not grant index permissions: every operation rechecks them.
        """
        window = preview_window(at=at, last_activity=last_activity, **self.window)
        now, boot = _instant(at, "at"), _instant(boot_at, "boot_at")
        if boot > now:
            raise ValueError("boot cannot be after at")
        reasons = list(window["reasons"])
        if (now - boot).total_seconds() < self.minimum_boot_minutes * 60:
            reasons.append("BOOT_RECENT")
        if load_ok is not True:
            reasons.append("LOAD_NOT_READY")
        stamp = now.timestamp()
        try:
            with exclusive_write(self.root, blocking=False), self._db() as db:
                s = self._load(db)
                if stamp < s["last_at"]:
                    db.execute("INSERT OR IGNORE INTO clock_fault VALUES (1,?)", (stamp,))
                fault = self._clock_fault(db)
                if fault is not None:
                    return self._report(s, "CLOCK_REVERSED", dict(review_required=True, clock_fault=fault))
                if reasons:
                    return self._report(s, "DEFERRED", {"reasons": reasons})
                if stamp < s["next_at"]:
                    return self._report(s, "WAITING")
                if s["outcome"] != "ACTIVE":
                    s = self._new(s["cycle"] + 1)
                s["last_at"] = stamp
                if self.index.embedding_id != self.context_options["model"]:
                    s["next_at"] = stamp+self.retry_seconds
                    s["last_result"] = {"state": "INDEX_INCOMPATIBLE", "detail": {}}
                    self._save(db, s)
                    return self._report(s, "INDEX_INCOMPATIBLE")
                try:
                    generation = self.index.active_generation()
                    if type(generation) is not str or not generation:
                        raise ValueError("invalid generation")
                except Exception as exc:
                    failure = "INDEX_INCOMPATIBLE" if isinstance(exc, IndexIncompatible) else "INDEX_UNAVAILABLE"
                    s["next_at"] = stamp+self.retry_seconds
                    s["last_result"] = {"state": failure, "detail": {}}
                    self._save(db, s)
                    return self._report(s, failure)
                if s["generation"] is not None and s["generation"] != generation:
                    s = self._new(s["cycle"] + 1)
                    s.update(generation=generation, last_at=stamp)
                    s["last_result"] = {"state": "RESTART_REQUIRED", "detail": {}}
                    self._save(db, s)
                    return self._report(s, "RESTART_REQUIRED")
                s["generation"] = generation
                state, detail = self._step(db, s, stamp)
                s["last_result"] = dict(state=state, detail=detail)
                self._save(db, s)
                return self._report(s, state, detail)
        except RepositoryBusy:
            return MaintenanceReport("BUSY", "UNKNOWN", 0, stamp+self.retry_seconds, {})

    def _step(self, db, s, now):
        stage = s["stage"]
        if stage in ("FIRST", "SECOND"):
            # Persist a fixed fence before the first effect of each pass.
            if s["through"] is None:
                s["through"] = self.journal.high_watermark()
                return "ACTIVE", {"stage": stage, "pass_started": s["through"]}
            page = self.worker.run_page(after=s["after"], through=s["through"], limit=self.page_size, now=now)
            s["after"] = page.after
            for seq, reason in page.result.deferred:
                db.execute("INSERT OR REPLACE INTO reviews VALUES (?,?,?)", (seq, reason, now))
            for seq in (*page.result.published, *page.result.indexed):
                db.execute("DELETE FROM reviews WHERE sequence=?", (seq,))
            s["progress"] += len(page.result.published) + len(page.result.indexed)
            if page.status not in ("MORE", "PASS_EXHAUSTED"):
                s["next_at"] = now + self.retry_seconds
                return page.status, asdict(page)
            if page.exhausted:
                s.update(stage="SECOND" if stage == "FIRST" else "CANONICAL", after=0, through=None)
            return "ACTIVE", asdict(page)
        if stage == "CANONICAL":
            if not s["canonical_done"]:
                try:
                    page = self.canonical.run_page(limit=self.page_size, restart=s["canonical_restart"])
                except CanonicalSnapshotUnavailable:
                    s.update(canonical_done=True, canonical_review=1, stage="ORPHANS")
                    return "ACTIVE", {"state": "SOURCE_REQUIRES_REVIEW", "inventory_completed": False}
                if page.state not in ("RUNNING", "VERIFYING", "COMPLETE", "REVIEW_REQUIRED", "RESTART_REQUIRED", "JOURNAL_FULL"):
                    s["next_at"] = now+self.retry_seconds
                    return page.state, asdict(page)
                s["canonical_restart"] = False
                s["canonical_done"] = page.state in ("COMPLETE", "REVIEW_REQUIRED")
                s["canonical_blocked"] = page.state == "JOURNAL_FULL"
                s["canonical_review"] = page.review_count
                s["progress"] += len(page.queued)
                detail = asdict(page)
            else:
                detail = {"state": "ALREADY_OBSERVED"}
            s["stage"] = "ORPHANS"
            return "ACTIVE", detail
        if stage == "ORPHANS":
            if not s["canonical_done"] and (not s["canonical_blocked"] or s["progress"]):
                s["stage"] = "FINISH"
                return "ACTIVE", {"state": "WAITING_FOR_CANONICAL"}
            if not s["orphan_done"]:
                page = self.orphans.run_page(limit=self.page_size, restart=s["orphan_restart"])
                if page.state not in ("RUNNING", "EXHAUSTED", "RESTART_REQUIRED", "LIMIT_REACHED"):
                    s["next_at"] = now+self.retry_seconds
                    return page.state, asdict(page)
                s["orphan_restart"] = False
                s["orphan_done"] = page.state in ("EXHAUSTED", "LIMIT_REACHED")
                s["orphan_review"] = page.review_count + int(page.state == "LIMIT_REACHED")
                detail = asdict(page)
            else:
                detail = {"state": "ALREADY_OBSERVED"}
            s["stage"] = "FINISH"
            return "ACTIVE", detail
        pending = bool(self.journal.pending(limit=1))
        done = s["canonical_done"] and s["orphan_done"] and not pending
        blocked = (s["canonical_done"] or s["canonical_blocked"]) and s["orphan_done"] and pending and not s["progress"]
        if done or blocked:
            s["outcome"] = "REVIEW_REQUIRED" if blocked or s["canonical_review"] or s["orphan_review"] else "CYCLE_COMPLETE"
            s["next_at"] = now+self.cycle_seconds
            return s["outcome"], {"pending": pending, "canonical_review": s["canonical_review"],
                                   "orphan_review": s["orphan_review"], "blocked": blocked}
        s.update(stage="FIRST", after=0, through=None, progress=0)
        return "ACTIVE", {"pending": pending, "next_round": True}

    def reviews(self, *, after=0, limit=100):
        """Historical reasons, filtered against current pending rows; no approval.

        An empty page may still have next_after when stale rows were pruned.
        Orphan observations use orphans.review_page() for fresh revalidation.
        """
        if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 999:
            raise ValueError("invalid review page")
        with exclusive_write(self.root, blocking=False), self._db() as db:
            self._load(db)
            rows = db.execute("SELECT sequence,reason,observed FROM reviews WHERE sequence>? ORDER BY sequence LIMIT ?", (after, limit+1)).fetchall()
            items = []
            for seq, reason, observed in rows[:limit]:
                intent = self.journal.intent(seq)
                if intent is None or intent.state not in ("INTENT", "PUBLISHED"):
                    db.execute("DELETE FROM reviews WHERE sequence=?", (seq,))
                else:
                    items.append(dict(sequence=seq, information_id=intent.information_id, reason=reason,
                                      observed=observed, current_state=intent.state))
            return dict(items=items, next_after=rows[limit-1][0] if len(rows) > limit else None)

    def status(self):
        """Historical checkpoint status only; does not probe the live index or grant rights."""
        with self._db() as db:
            s = self._load(db)
            fault = self._clock_fault(db)
            detail = dict(last_at=s["last_at"], last_result=s["last_result"])
            if fault is not None:
                detail["clock_fault"] = fault
            return self._report(s, "REVIEW_REQUIRED" if fault is not None else s["outcome"], detail)

    @staticmethod
    def _clock_fault(db):
        row = db.execute("SELECT observed_at FROM clock_fault WHERE singleton=1").fetchone()
        return None if row is None else dict(reason="CLOCK_REVERSED", observed_at=row[0])

    def recover_clock(self, *, at, expected_last_at, expected_cycle, actor, reason, request_id):
        """Explicit host/operator decision, atomic with its audit receipt.

        The host must authenticate/authorize its operator before calling this API;
        actor is an audit label, not a credential. No journal timestamp, canonical
        file or index point is changed. All scans restart on later eligible ticks.
        The same request may be retried; a different decision needs a new ID.
        """
        stamp = _instant(at, "at").timestamp()
        if (not 0 <= stamp < float("inf")
                or type(expected_last_at) not in (int, float)
                or not 0 <= expected_last_at < float("inf")
                or type(expected_cycle) is not int or expected_cycle < 1
                or any(type(v) is not str or not v.strip() or len(v) > bound
                       or any(ord(c) < 32 or ord(c) == 127 for c in v)
                       for v, bound in ((actor, 128), (reason, 512)))
                or type(request_id) is not str
                or re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", request_id) is None):
            raise ValueError("invalid clock recovery decision")
        decision = dict(request_id=request_id, actor=actor, reason=reason, at=stamp,
                        previous_last_at=expected_last_at, previous_cycle=expected_cycle)
        with exclusive_write(self.root, blocking=False), self._db() as db:
            s = self._load(db)
            existing = db.execute("SELECT receipt FROM clock_recoveries WHERE request_id=?", (request_id,)).fetchone()
            if existing:
                receipt = json.loads(existing[0])
                if any(receipt[k] != v for k, v in decision.items()):
                    raise ValueError("clock recovery request ID already used")
                return receipt
            if (self._clock_fault(db) is None or s["last_at"] != expected_last_at
                    or s["cycle"] != expected_cycle or stamp >= s["last_at"]):
                raise ValueError("clock recovery requires a current fault and matching state")
            receipt = dict(decision, cycle=s["cycle"]+1)
            cursor = db.execute("INSERT INTO clock_recoveries (request_id,receipt) VALUES (?,?)",
                                (request_id, json.dumps(receipt, allow_nan=False)))
            receipt["sequence"] = cursor.lastrowid
            db.execute("UPDATE clock_recoveries SET receipt=? WHERE sequence=?",
                       (json.dumps(receipt, allow_nan=False), cursor.lastrowid))
            fresh = self._new(s["cycle"]+1)
            fresh.update(last_at=stamp, next_at=stamp,
                         last_result=dict(state="CLOCK_RECOVERED", detail=dict(request_id=request_id)))
            self._save(db, fresh)
            db.execute("DELETE FROM clock_fault WHERE singleton=1")
            return receipt

    def clock_recoveries(self, *, after=0, limit=100):
        """Bounded historical audit; does not contact the index or authorize work."""
        if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 999:
            raise ValueError("invalid clock recovery page")
        with self._db() as db:
            self._load(db)
            rows = db.execute("SELECT sequence,receipt FROM clock_recoveries WHERE sequence>? ORDER BY sequence LIMIT ?",
                              (after, limit+1)).fetchall()
            return dict(items=[json.loads(row[1]) for row in rows[:limit]],
                        next_after=rows[limit-1][0] if len(rows) > limit else None)
