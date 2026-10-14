"""Canonical reader integration on disposable Markdown files only."""
from hashlib import sha256
import pytest
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.indexing.worker_canonical import CanonicalReader
from core.indexing.worker_upsert import apply_upsert
from core.indexing.reconcile_plan import Action


class FakeIndex:
    def __init__(self):
        self.writes = []
    def upsert(self, memory):
        self.writes.append((memory.information_id, memory.revision))


def test_canonical_file_reader_and_worker_upsert(tmp_path):
    persistent, history = tmp_path / "persistent", tmp_path / "history"
    backend = FilesystemBackend(persistent, history)
    backend.store(Memory("doc", content="canonical text"))
    reader = CanonicalReader(persistent)
    memory, digest = reader("doc")
    assert digest == sha256((persistent / "doc.md").read_bytes()).hexdigest()
    index = FakeIndex()
    receipt = apply_upsert(
        Action("ENQUEUE_UPSERT", "doc", None, memory.revision, "manifest"),
        read_canonical=reader, authorize=lambda *args: True, index=index,
        profile_id="owner", model_id="embedding-v1",
        expected_model_id="embedding-v1", expected_profile_id="owner",
        expected_sha256=digest)
    assert receipt.state == "ACKNOWLEDGED"
    assert index.writes == [("doc", memory.revision)]


def test_canonical_symlink_refused(tmp_path):
    persistent, history = tmp_path / "persistent", tmp_path / "history"
    backend = FilesystemBackend(persistent, history)
    backend.store(Memory("doc", content="original"))
    (persistent / "link.md").symlink_to(persistent / "doc.md")
    with pytest.raises(ValueError, match="unsafe"):
        CanonicalReader(persistent)("link")


def test_canonical_revision_drift_blocks_index(tmp_path):
    persistent, history = tmp_path / "persistent", tmp_path / "history"
    backend = FilesystemBackend(persistent, history)
    backend.store(Memory("doc", content="original"))
    reader = CanonicalReader(persistent)
    _, digest = reader("doc")
    backend.update("doc", content="changed", expected_revision=1)
    index = FakeIndex()
    result = apply_upsert(
        Action("ENQUEUE_UPSERT", "doc", None, 1, "old manifest"),
        read_canonical=reader, authorize=lambda *args: True, index=index,
        profile_id="owner", model_id="embedding-v1",
        expected_model_id="embedding-v1", expected_profile_id="owner",
        expected_sha256=digest)
    assert result.state == "REFUSED"
    assert index.writes == []
