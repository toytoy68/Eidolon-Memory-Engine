"""C201: offline canonical replay probes for the derived FTS5 candidate index.

These tests do NOT claim compatibility with JournalUpsertWorker. They validate
the separate snapshot/rebuild path prior to a future verified worker adapter.
"""
from hashlib import sha256
import json
import multiprocessing

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.indexing.fts5_index import SqliteFts5Index


def _canonical(tmp_path):
    return FilesystemBackend(
        persistent_root=tmp_path / "canonical",
        history_root=tmp_path / "history",
    )


def test_offline_replay_restores_latest_canonical_revision(tmp_path):
    backend = _canonical(tmp_path)
    backend.store(Memory("event", content="initial apple"))
    index = SqliteFts5Index(tmp_path / "derived.db")
    index.rebuild(tmp_path / "canonical")
    assert [x.information_id for x in index.query("apple")] == ["event"]

    backend.update("event", Memory("event", content="updated banana"), 1)
    # Deliberately stale until the separately requested rebuild:
    assert [x.information_id for x in index.query("apple")] == ["event"]
    index.rebuild(tmp_path / "canonical")
    assert not index.query("apple")
    assert [x.information_id for x in index.query("banana")] == ["event"]


def test_rebuild_corrupt_canonical_preserves_previous_snapshot(tmp_path):
    backend = _canonical(tmp_path)
    backend.store(Memory("safe", content="retained atlas"))
    index = SqliteFts5Index(tmp_path / "derived.db")
    index.rebuild(tmp_path / "canonical")
    original = index.query("atlas")
    (tmp_path / "canonical" / "safe.md").write_bytes(b"corrupt non-memory content")
    with pytest.raises(Exception):
        index.rebuild(tmp_path / "canonical")
    assert index.query("atlas") == original


def test_reopening_index_keeps_private_file_mode(tmp_path):
    backend = _canonical(tmp_path)
    backend.store(Memory("protected", content="alpha"))
    path = tmp_path / "index.db"
    index = SqliteFts5Index(path)
    index.rebuild(tmp_path / "canonical")
    assert (path.stat().st_mode & 0o077) == 0
    opened = SqliteFts5Index(path)
    assert [x.information_id for x in opened.query("alpha")] == ["protected"]
