"""C205: multiprocess generation and process-kill recovery probes.

All work uses disposable tmp_path SQLite and canonical Markdown data.
"""
import multiprocessing as mp
import os
import sqlite3
import time

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.indexing.fts5_verified_experimental import VerifiedSqliteFts5Index


def _writer(path, queue, repetitions):
    try:
        index = VerifiedSqliteFts5Index(path, alias="eidolon_c205")
        for i in range(repetitions):
            index.upsert_verified(Memory(f"writer-{os.getpid()}", content=f"write {i}", revision=i+1),
                                  canonical_sha256=f"{i % 10}" * 64)
        queue.put(("writer", None))
    except Exception as exc:
        queue.put(("writer", repr(exc)))


def _rebuild(path, root, queue, repetitions):
    try:
        index = VerifiedSqliteFts5Index(path, alias="eidolon_c205")
        for _ in range(repetitions):
            index.rebuild(root)
        queue.put(("rebuild", None))
    except Exception as exc:
        queue.put(("rebuild", repr(exc)))


def _abrupt_exit(path):
    index = VerifiedSqliteFts5Index(path, alias="eidolon_c205")
    # Simulate process failure BEFORE committing any changed SQLite transaction.
    try:
        with index._open(index.path) as db:
            db.execute("INSERT OR REPLACE INTO meta VALUES('generation','eidolon_c205__interrupted')")
            os._exit(137)
    finally:
        os._exit(138)


def test_cross_process_rebuild_and_updates(tmp_path):
    root = tmp_path / "canonical"
    backend = FilesystemBackend(root, tmp_path / "history")
    for i in range(8):
        backend.store(Memory(f"base-{i}", content="stable alpha"))
    path = tmp_path / "fts5.db"
    index = VerifiedSqliteFts5Index(path, alias="eidolon_c205")
    index.rebuild(root)
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    jobs = [
        ctx.Process(target=_rebuild, args=(path, root, q, 10)),
        ctx.Process(target=_writer, args=(path, q, 30)),
        ctx.Process(target=_writer, args=(path, q, 30)),
    ]
    for job in jobs: job.start()
    for job in jobs:
        job.join(20)
        if job.is_alive():
            job.terminate()
            job.join(5)
        assert job.exitcode == 0
    results = [q.get(timeout=2) for _ in jobs]
    assert all(err is None for _, err in results), results
    reopened = VerifiedSqliteFts5Index(path, alias="eidolon_c205")
    generation = reopened.active_generation()
    page = reopened.inventory_page(generation=generation, limit=100)
    for record in page.records:
        if record.evidence is not None:
            assert record.evidence.generation == generation
            assert record.evidence.revision == record.revision
    assert reopened.status().documents >= 8


def test_process_crash_during_uncommitted_generation_change(tmp_path):
    path = tmp_path / "fts5.db"
    index = VerifiedSqliteFts5Index(path, alias="eidolon_c205")
    prior = index.active_generation()
    ctx = mp.get_context("spawn")
    proc = ctx.Process(target=_abrupt_exit, args=(path,))
    proc.start()
    proc.join(10)
    assert proc.exitcode == 137
    reopened = VerifiedSqliteFts5Index(path, alias="eidolon_c205")
    assert reopened.active_generation() == prior
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
