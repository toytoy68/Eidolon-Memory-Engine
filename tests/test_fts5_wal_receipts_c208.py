"""C208 WAL contention and receipt consistency in disposable SQLite snapshots."""
import os
import sqlite3
import pytest
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.indexing.fts5_verified_experimental import VerifiedSqliteFts5Index
from core.indexing.manifest import build_manifest
import core.indexing.fts5_index as fts


def setup(tmp_path):
    root = tmp_path / "canonical"
    backend = FilesystemBackend(root, tmp_path / "history")
    backend.store(Memory("first", content="first apple"))
    index = VerifiedSqliteFts5Index(tmp_path / "index.db", alias="eidolon_c208")
    return index, root, backend


def test_receipt_matches_canonical_manifest_on_success(tmp_path):
    index, root, backend = setup(tmp_path)
    receipt = index.rebuild_with_receipt(root)
    assert receipt.state == "PUBLISHED"
    assert receipt.source_digest == build_manifest(root).digest
    assert receipt.generation == index.active_generation()
    assert index.status().source_digest == receipt.source_digest
    backend.store(Memory("second", content="second orange"))
    again = index.rebuild_with_receipt(root)
    assert again.state == "PUBLISHED"
    assert again.generation != receipt.generation
    assert again.source_digest == build_manifest(root).digest


def test_staging_wal_checkpoint_is_handled_before_replace(tmp_path, monkeypatch):
    index, root, _ = setup(tmp_path)
    original = fts.SqliteFts5Index._initialise.__func__
    def wal_initialise(cls, path):
        original(cls, path)
        if str(path).endswith(".rebuild"):
            with sqlite3.connect(path) as db:
                db.execute("PRAGMA journal_mode=WAL")
    monkeypatch.setattr(fts.SqliteFts5Index, "_initialise", classmethod(wal_initialise))
    receipt = index.rebuild_with_receipt(root)
    assert receipt.state == "PUBLISHED"
    with sqlite3.connect(index.path) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("SELECT count(*) FROM documents").fetchone()[0] == 1


def test_unreadable_rebuild_is_not_reported_as_published(tmp_path, monkeypatch):
    index, root, _ = setup(tmp_path)
    first = index.rebuild_with_receipt(root)
    original = fts.os.replace
    monkeypatch.setattr(fts.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("blocked")))
    attempt = index.rebuild_with_receipt(root)
    assert attempt.state == "NOT_PUBLISHED"
    assert attempt.generation == first.generation
    monkeypatch.setattr(fts.os, "replace", original)
