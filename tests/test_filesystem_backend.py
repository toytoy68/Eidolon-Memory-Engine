import json

import pytest

from core.backend.errors import InvalidMemory, MemoryAlreadyExists, RevisionConflict
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory


def test_backend_rejects_symlinked_information_without_reading_target(tmp_path):
    backend = FilesystemBackend(tmp_path / "persistent", tmp_path / "history")
    outside = tmp_path / "outside.md"
    outside.write_text(FilesystemBackend._serialize(Memory("info-test", content="private")))
    path = backend.persistent_root / "info-test.md"
    path.symlink_to(outside)
    with pytest.raises(InvalidMemory, match="symlink"):
        backend.get("info-test")
    with pytest.raises(InvalidMemory, match="symlink"):
        backend.exists("info-test")
    with pytest.raises(MemoryAlreadyExists):
        backend.store(Memory("info-test", content="replacement"))
    assert backend.list() == []
    assert outside.read_text().find("private") != -1


def test_backend_rejects_symlinked_storage_directories(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    persistent = tmp_path / "persistent"
    persistent.symlink_to(outside, target_is_directory=True)
    with pytest.raises(InvalidMemory, match="directory is a symlink"):
        FilesystemBackend(persistent, tmp_path / "history")
    persistent.unlink()
    history = tmp_path / "history"
    history.symlink_to(outside, target_is_directory=True)
    with pytest.raises(InvalidMemory, match="directory is a symlink"):
        FilesystemBackend(persistent, history)


def test_list_and_search_skip_identity_mismatch(tmp_path):
    backend = FilesystemBackend(tmp_path / "persistent", tmp_path / "history")
    backend.store(Memory("actual", content="unique searchable content"))
    (backend.persistent_root / "actual.md").rename(backend.persistent_root / "wrong.md")
    with pytest.raises(InvalidMemory, match="identity"):
        backend.get("wrong")
    assert backend.list() == []
    assert backend.search("unique searchable") == []


def test_search_considers_information_after_ten_thousand_entries(tmp_path, monkeypatch):
    backend = FilesystemBackend(tmp_path / "persistent", tmp_path / "history")

    def documents():
        for index in range(10_000):
            yield Memory(f"info-{index}", content="ordinary")
        yield Memory("final", content="rare-search-term")

    monkeypatch.setattr(backend, "_iter_valid_memories", documents)
    matches = backend.search("rare-search-term")
    assert [result.memory.information_id for result in matches] == ["final"]


def test_list_stops_after_requested_filtered_page(tmp_path, monkeypatch):
    backend = FilesystemBackend(tmp_path / "persistent", tmp_path / "history")
    visited = []

    def documents():
        for index in range(100):
            visited.append(index)
            yield Memory(f"info-{index}", metadata={"group": "match" if index % 2 else "other"})

    monkeypatch.setattr(backend, "_iter_valid_memories", documents)
    page = backend.list(offset=2, limit=2, filters={"group": "match"})
    assert [memory.information_id for memory in page] == ["info-5", "info-7"]
    assert visited == list(range(8))


def test_backend_rejects_boolean_revision_before_writing(tmp_path):
    backend = FilesystemBackend(tmp_path / "persistent", tmp_path / "history")
    with pytest.raises(InvalidMemory, match="revision must be an integer"):
        backend.store(Memory("info-test", revision=True))
    assert not (backend.persistent_root / "info-test.md").exists()
    backend.store(Memory("info-test", content="original"))
    replacement = Memory("info-test", content="replacement")
    with pytest.raises(InvalidMemory, match="previous_revision"):
        backend.update("info-test", replacement, previous_revision=True)
    assert replacement.revision == 1
    assert backend.get("info-test").content == "original"


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


@pytest.mark.parametrize("interrupt_after", ["marker", "unlink"])
def test_approve_delete_recovers_interruption(tmp_path, monkeypatch, interrupt_after):
    backend = FilesystemBackend(tmp_path / "persistent", tmp_path / "history")
    backend.store(Memory("info-test", content="keep"))
    backend.delete_request("info-test", "human", "reason", 1, "op-1")
    receipt = tmp_path / "history/pending-delete/info-test.json"
    original_write = backend._atomic_write
    if interrupt_after == "marker":
        def interrupted_write(path, content):
            original_write(path, content)
            if path == receipt and '"APPLYING_DELETE"' in content:
                raise RuntimeError("simulated stop after journal")
        monkeypatch.setattr(backend, "_atomic_write", interrupted_write)
    else:
        original_unlink = type(backend._path("info-test")).unlink
        def interrupted_unlink(path, *args, **kwargs):
            result = original_unlink(path, *args, **kwargs)
            if path == backend._path("info-test"):
                raise RuntimeError("simulated stop after unlink")
            return result
        monkeypatch.setattr(type(backend._path("info-test")), "unlink", interrupted_unlink)
    with pytest.raises(RuntimeError, match="simulated stop"):
        backend.approve_delete("info-test", "op-1")
    monkeypatch.undo()
    assert json.loads(receipt.read_text())["status"] == "APPLYING_DELETE"
    assert backend.approve_delete("info-test", "op-1").status == "DELETED"
    assert not backend.exists("info-test")


def test_approve_delete_recovery_rejects_changed_information(tmp_path, monkeypatch):
    backend = FilesystemBackend(tmp_path / "persistent", tmp_path / "history")
    backend.store(Memory("info-test", content="keep"))
    backend.delete_request("info-test", "human", "reason", 1, "op-1")
    receipt = tmp_path / "history/pending-delete/info-test.json"
    original_write = backend._atomic_write
    def stop_at_marker(path, content):
        original_write(path, content)
        if path == receipt and '"APPLYING_DELETE"' in content:
            raise RuntimeError("stop")
    monkeypatch.setattr(backend, "_atomic_write", stop_at_marker)
    with pytest.raises(RuntimeError):
        backend.approve_delete("info-test", "op-1")
    monkeypatch.undo()
    backend._path("info-test").write_text("replacement")
    with pytest.raises(RevisionConflict, match="changed during deletion"):
        backend.approve_delete("info-test", "op-1")
    assert backend._path("info-test").read_text() == "replacement"
    with pytest.raises(RevisionConflict, match="not pending"):
        backend.cancel_delete("info-test", "op-1")


@pytest.mark.parametrize("field,value", [("requested_by", None), ("reason", ""),
                                           ("operation_id", ""), ("revision", True)])
def test_new_deletion_request_rejects_unusable_fields(tmp_path, field, value):
    backend = FilesystemBackend(tmp_path / "persistent", tmp_path / "history")
    backend.store(Memory("info-test"))
    fields = {"requested_by": "human", "reason": "because", "revision": 1,
              "operation_id": "op-1"}
    fields[field] = value
    with pytest.raises(InvalidMemory, match="invalid deletion request fields"):
        backend.delete_request("info-test", **fields)
    assert not (backend.pending_delete_root / "info-test.json").exists()


@pytest.mark.parametrize("field,value", [("requested_by", None), ("reason", "")])
def test_malformed_deletion_receipt_cannot_approve(tmp_path, field, value):
    backend = FilesystemBackend(tmp_path / "persistent", tmp_path / "history")
    backend.store(Memory("info-test"))
    backend.delete_request("info-test", "human", "because", 1, "op-1")
    receipt = backend.pending_delete_root / "info-test.json"
    record = json.loads(receipt.read_text())
    record[field] = value
    receipt.write_text(json.dumps(record))
    with pytest.raises(InvalidMemory, match="invalid"):
        backend.approve_delete("info-test", "op-1")
    assert backend.exists("info-test")
