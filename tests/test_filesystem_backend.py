import json

import pytest

from core.backend.errors import InvalidMemory, RevisionConflict
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


def test_pending_delete_request_replay_does_not_write_again(tmp_path, monkeypatch):
    backend = FilesystemBackend(tmp_path / "persistent", tmp_path / "history")
    backend.store(Memory("info-test"))
    backend.delete_request("info-test", "human", "reason", 1, "op-1")

    def unexpected_write(*args):
        raise AssertionError("identical request should not write")

    monkeypatch.setattr(backend, "_atomic_write", unexpected_write)
    assert backend.delete_request("info-test", "human", "reason", 1, "op-1").status == "PENDING_DELETE"


def test_second_pending_delete_request_cannot_replace_first(tmp_path):
    backend = FilesystemBackend(tmp_path / "persistent", tmp_path / "history")
    backend.store(Memory("info-test"))
    backend.delete_request("info-test", "human", "reason", 1, "op-1")
    path = tmp_path / "history/pending-delete/info-test.json"
    before = path.read_bytes()

    with pytest.raises(RevisionConflict, match="another deletion request"):
        backend.delete_request("info-test", "other", "new reason", 1, "op-2")
    assert path.read_bytes() == before
    assert json.loads(path.read_text())["operation_id"] == "op-1"


def test_invalid_delete_request_receipt_is_not_overwritten(tmp_path):
    backend = FilesystemBackend(tmp_path / "persistent", tmp_path / "history")
    backend.store(Memory("info-test"))
    path = tmp_path / "history/pending-delete/info-test.json"
    path.write_text("broken")
    with pytest.raises(InvalidMemory, match="unreadable"):
        backend.delete_request("info-test", "human", "reason", 1, "op-1")
    assert path.read_text() == "broken"


@pytest.mark.parametrize("decision", ["approve_delete", "cancel_delete"])
def test_delete_decision_rejects_receipt_with_wrong_information_id(tmp_path, decision):
    backend = FilesystemBackend(tmp_path / "persistent", tmp_path / "history")
    backend.store(Memory("info-test", content="keep"))
    backend.delete_request("info-test", "human", "reason", 1, "op-1")
    path = tmp_path / "history/pending-delete/info-test.json"
    record = json.loads(path.read_text())
    record["information_id"] = "other-info"
    path.write_text(json.dumps(record))
    before = path.read_bytes()

    with pytest.raises(InvalidMemory, match="identity mismatch"):
        getattr(backend, decision)("info-test", "op-1")
    assert backend.get("info-test").content == "keep"
    assert path.read_bytes() == before


@pytest.mark.parametrize("decision", ["approve_delete", "cancel_delete"])
def test_delete_decision_rejects_unreadable_receipt(tmp_path, decision):
    backend = FilesystemBackend(tmp_path / "persistent", tmp_path / "history")
    backend.store(Memory("info-test", content="keep"))
    backend.delete_request("info-test", "human", "reason", 1, "op-1")
    path = tmp_path / "history/pending-delete/info-test.json"
    path.write_text("broken")

    with pytest.raises(InvalidMemory, match="unreadable"):
        getattr(backend, decision)("info-test", "op-1")
    assert backend.get("info-test").content == "keep"
    assert path.read_text() == "broken"
