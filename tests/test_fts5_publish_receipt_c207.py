"""C207 publication receipt and SQLite journal inspection."""
import os
import sqlite3
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.indexing.fts5_verified_experimental import VerifiedSqliteFts5Index
import core.indexing.fts5_index as fts


def setup(tmp_path):
    root=tmp_path/"canonical"
    backend=FilesystemBackend(root,tmp_path/"history")
    backend.store(Memory("a",content="first"))
    idx=VerifiedSqliteFts5Index(tmp_path/"index.db",alias="eidolon_c207")
    return idx,root,backend


def test_receipt_success_and_pre_replace_failure(tmp_path,monkeypatch):
    idx,root,backend=setup(tmp_path)
    first=idx.rebuild_with_receipt(root)
    assert first.state=="PUBLISHED"
    assert first.generation==idx.active_generation()
    backend.store(Memory("b",content="second"))
    original=fts.os.replace
    def fail(*args):
        raise OSError("before replace")
    monkeypatch.setattr(fts.os,"replace",fail)
    failed=idx.rebuild_with_receipt(root)
    assert failed.state=="NOT_PUBLISHED"
    assert failed.generation==first.generation
    monkeypatch.setattr(fts.os,"replace",original)


def test_receipt_after_replace_fsync_failure(tmp_path,monkeypatch):
    idx,root,backend=setup(tmp_path)
    idx.rebuild_with_receipt(root)
    backend.store(Memory("b",content="second"))
    original=fts.os.fsync
    def fail_dir(fd):
        if os.path.isdir(f"/proc/self/fd/{fd}"):
            raise OSError("simulated directory fsync failure")
        return original(fd)
    monkeypatch.setattr(fts.os,"fsync",fail_dir)
    result=idx.rebuild_with_receipt(root)
    monkeypatch.setattr(fts.os,"fsync",original)
    assert result.state=="PUBLISHED_UNCONFIRMED"
    assert idx.active_generation()==result.generation
    assert idx.status().source_digest==result.source_digest


def test_sqlite_journal_mode_and_integrity(tmp_path):
    idx,root,_=setup(tmp_path)
    idx.rebuild_with_receipt(root)
    with sqlite3.connect(idx.path) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
        assert db.execute("PRAGMA journal_mode").fetchone()[0] in ("delete","wal","truncate","persist")
