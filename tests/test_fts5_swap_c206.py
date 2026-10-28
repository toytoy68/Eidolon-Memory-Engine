"""C206 failure-injection probes for SQLite atomic replacement."""
import os
import sqlite3
import pytest
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.indexing.fts5_verified_experimental import VerifiedSqliteFts5Index
import core.indexing.fts5_index as fts


def setup_index(tmp_path):
    root=tmp_path/"canon"
    backend=FilesystemBackend(root,tmp_path/"history")
    backend.store(Memory("a",content="original kiwi"))
    index=VerifiedSqliteFts5Index(tmp_path/"idx.db",alias="eidolon_c206")
    index.rebuild(root)
    return index,root,backend


def test_failure_before_replace_keeps_old_index(tmp_path,monkeypatch):
    index,root,backend=setup_index(tmp_path)
    backend.store(Memory("b",content="new mango"))
    old=index.active_generation()
    def interrupted(source,target):
        raise OSError("simulated pre-replace crash")
    monkeypatch.setattr(fts.os,"replace",interrupted)
    with pytest.raises(OSError,match="pre-replace"):
        index.rebuild(root)
    assert index.active_generation()==old
    assert [x.information_id for x in index.query("kiwi")]==["a"]
    assert index.query("mango")==[]


def test_open_sqlite_connection_survives_swap_as_old_snapshot(tmp_path):
    index,root,backend=setup_index(tmp_path)
    old=sqlite3.connect(index.path)
    assert old.execute("select count(*) from documents").fetchone()[0]==1
    backend.store(Memory("b",content="new mango"))
    index.rebuild(root)
    assert old.execute("select count(*) from documents").fetchone()[0]==1
    assert index.status().documents==2
    assert index.query("mango")
    old.close()
