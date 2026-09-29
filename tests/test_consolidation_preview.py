import pytest

from core.backend.errors import InvalidMemory
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.information.consolidation import preview_exact_duplicates


def test_exact_duplicate_preview_preserves_divergent_history(tmp_path):
    backend = FilesystemBackend(tmp_path / "persistent", tmp_path / "history")
    backend.store(Memory("one", content="same private text", revision=1,
                         metadata={"epistemic_status": "CONFIRMED"},
                         provenance={"source": "human"}))
    backend.store(Memory("two", content="same private text", revision=2,
                         metadata={"epistemic_status": "REFUTED"},
                         provenance={"source": "test"}))
    backend.store(Memory("three", content="different private text"))
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    preview = preview_exact_duplicates(backend.persistent_root)
    assert len(preview.groups) == 1
    assert preview.groups[0].information_ids == ("one", "two")
    assert preview.groups[0].differing_fields == ("revision", "metadata", "provenance")
    assert "private" not in repr(preview)
    assert {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before


def test_exact_duplicate_preview_rejects_linked_source(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = tmp_path / "persistent"
    linked.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinked"):
        preview_exact_duplicates(linked)


def test_exact_duplicate_preview_rejects_invalid_information(tmp_path):
    persistent = tmp_path / "persistent"
    persistent.mkdir()
    (persistent / "bad.md").write_text("private malformed")
    with pytest.raises(InvalidMemory):
        preview_exact_duplicates(persistent)
