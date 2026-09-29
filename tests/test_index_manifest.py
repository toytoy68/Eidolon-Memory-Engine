import pytest

from core.backend.errors import InvalidMemory
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.indexing import build_manifest


def test_manifest_is_stable_and_detects_source_change(tmp_path):
    backend = FilesystemBackend(tmp_path / "persistent", tmp_path / "history")
    backend.store(Memory("b", content="private beta"))
    backend.store(Memory("a", content="private alpha"))
    first = build_manifest(backend.persistent_root)
    assert [item.information_id for item in first.entries] == ["a", "b"]
    assert build_manifest(backend.persistent_root) == first
    assert "private" not in repr(first)
    backend.update("a", Memory("a", content="new private alpha"), previous_revision=1)
    second = build_manifest(backend.persistent_root)
    assert second.digest != first.digest
    assert second.entries[0].revision == 2
    assert second.entries[1] == first.entries[1]


def test_manifest_blocks_invalid_or_symlinked_source(tmp_path):
    persistent = tmp_path / "persistent"
    persistent.mkdir()
    (persistent / "wrong.md").write_text(FilesystemBackend._serialize(Memory("different")))
    with pytest.raises(InvalidMemory, match="identity mismatch"):
        build_manifest(persistent)
    (persistent / "wrong.md").unlink()
    external = tmp_path / "external.md"
    external.write_text("private")
    (persistent / "linked.md").symlink_to(external)
    with pytest.raises(InvalidMemory, match="unsafe path"):
        build_manifest(persistent)
    assert external.read_text() == "private"
    (persistent / "linked.md").unlink()
    persistent.rmdir()
    persistent.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="real directory"):
        build_manifest(persistent)
