"""Subclass IndexPortContract unchanged for each index adapter."""

from pathlib import Path

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.indexing.manifest import build_manifest


class IndexPortContract:
    @pytest.fixture
    def index(self):
        raise NotImplementedError("adapter test must provide an index fixture")

    def test_upsert_query_and_delete(self, index):
        index.upsert(Memory("a", content="refroidissement eau"))
        index.upsert(Memory("b", content="stockage disques"))
        assert "a" in [hit.information_id for hit in index.query("refroidissement", limit=5)]
        index.upsert(Memory("a", content="réseau fibre"))
        assert index.status().documents == 2
        assert "a" in [hit.information_id for hit in index.query("réseau fibre", limit=5)]
        index.delete("a")
        index.delete("a")
        assert "a" not in [hit.information_id for hit in index.query("réseau", limit=5)]
        assert index.status().documents == 1

    def test_rebuild_from_canonical_files_and_status(self, index, tmp_path):
        persistent = tmp_path / "memory/persistent"
        backend = FilesystemBackend(persistent, tmp_path / "memory/history")
        backend.store(Memory("first", content="moteur robotique"))
        before = {path: path.read_bytes() for path in persistent.glob("*.md")}
        index.upsert(Memory("stale", content="moteur robotique"))
        index.rebuild(persistent)
        assert "first" in [hit.information_id for hit in index.query("robotique", limit=5)]
        assert index.status().documents == 1
        assert index.status().source_digest == build_manifest(persistent).digest
        assert {path: path.read_bytes() for path in persistent.glob("*.md")} == before
        assert "stale" not in [hit.information_id for hit in index.query("stale", limit=5)]

    def test_failed_rebuild_preserves_previous_index(self, index, tmp_path):
        index.upsert(Memory("safe", content="système hydraulique"))
        persistent = tmp_path / "persistent"
        persistent.mkdir()
        (persistent / "broken.md").write_text("invalid")
        with pytest.raises(Exception):
            index.rebuild(persistent)
        assert "safe" in [hit.information_id for hit in index.query("hydraulique", limit=5)]
