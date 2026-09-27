import pytest

from core.backend.errors import RevisionConflict
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory


def test_store_and_get(tmp_path):
    backend = FilesystemBackend(
        persistent_root=tmp_path / "persistent",
        history_root=tmp_path / "history",
    )

    memory = Memory(
        information_id="info-test",
        content="Contenu de test",
        metadata={"type": "FACT"},
    )

    result = backend.store(memory)

    assert result.information_id == "info-test"
    assert result.revision == 1

    loaded = backend.get("info-test")

    assert loaded is not None
    assert loaded.information_id == "info-test"
    assert loaded.revision == 1
    assert loaded.content == "Contenu de test"
    assert loaded.metadata == {"type": "FACT"}

def test_update_increments_revision(tmp_path):
    backend = FilesystemBackend(
        persistent_root=tmp_path / "persistent",
        history_root=tmp_path / "history",
    )

    backend.store(
        Memory(
            information_id="info-test",
            content="Version 1",
        )
    )

    updated = Memory(
        information_id="info-test",
        content="Version 2",
    )

    result = backend.update(
        "info-test",
        updated,
        previous_revision=1,
    )

    assert result.previous_revision == 1
    assert result.revision == 2

    loaded = backend.get("info-test")

    assert loaded is not None
    assert loaded.revision == 2
    assert loaded.content == "Version 2"

def test_update_rejects_revision_conflict(tmp_path):
    backend = FilesystemBackend(
        persistent_root=tmp_path / "persistent",
        history_root=tmp_path / "history",
    )

    backend.store(
        Memory(
            information_id="info-test",
            content="Version 1",
        )
    )

    backend.update(
        "info-test",
        Memory(
            information_id="info-test",
            content="Version 2",
        ),
        previous_revision=1,
    )

    with pytest.raises(RevisionConflict):
        backend.update(
            "info-test",
            Memory(
                information_id="info-test",
                content="Version 3",
            ),
            previous_revision=1,
        )

def test_delete_request_creates_pending_delete(tmp_path):
    backend = FilesystemBackend(
        persistent_root=tmp_path / "persistent",
        history_root=tmp_path / "history",
    )

    backend.store(
        Memory(
            information_id="info-test",
            content="Contenu",
        )
    )

    result = backend.delete_request(
        "info-test",
        requested_by="test",
        reason="test deletion",
        revision=1,
        operation_id="op-test",
    )

    assert result.information_id == "info-test"
    assert result.status == "PENDING_DELETE"

    pending = tmp_path / "history" / "pending-delete" / "info-test.json"
    assert pending.exists()

    assert backend.exists("info-test")
