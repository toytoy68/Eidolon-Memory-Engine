"""C206 publish boundary: replacement happened but directory fsync failed."""
import os
import sqlite3
import pytest
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.indexing.fts5_verified_experimental import VerifiedSqliteFts5Index
import core.indexing.fts5_index as fts


def test_failure_after_replace_is_not_rollback(tmp_path, monkeypatch):
    root=tmp_path/"canon"
    backend=FilesystemBackend(root,tmp_path/"history")
    backend.store(Memory("a",content="old peach"))
    idx=VerifiedSqliteFts5Index(tmp_path/"idx.db",alias="eidolon_after")
    idx.rebuild(root)
    backend.store(Memory("b",content="fresh papaya"))
    original_fsync=os.fsync
    def fail_directory_fsync(fd):
        if os.path.isdir(f"/proc/self/fd/{fd}"):
            raise OSError("simulated directory fsync failed")
        return original_fsync(fd)
    monkeypatch.setattr(fts.os,"fsync",fail_directory_fsync)
    with pytest.raises(OSError,match="fsync failed"):
        idx.rebuild(root)
    monkeypatch.setattr(fts.os,"fsync",original_fsync)
    recovered=VerifiedSqliteFts5Index(idx.path,alias="eidolon_after")
    assert recovered.query("papaya")
    assert recovered.status().documents==2
    assert recovered.evidence_for("b") is None
