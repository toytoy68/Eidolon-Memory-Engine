"""Full Information → Thread → journal → Event → recovery lifecycle on a copy."""

import pytest

from core.backend.errors import InformationDeletionBlocked
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.events.filesystem import FilesystemEventRepository
from core.operations.filesystem import FilesystemOperationRepository
from core.operations.models import OperationStatus
from core.operations.thread_create import FilesystemLinkedThreadCreation
from core.operations.thread_delete import FilesystemThreadDeletion
from core.operations.thread_status import FilesystemThreadOperations
from core.threads.models import Thread, ThreadStatus
from core.threads.service import ThreadService
from core.threads.storage import ThreadStorage


def open_service(root):
    persistent, history = root / "memory/persistent", root / "memory/history"
    backend = FilesystemBackend(persistent, history)
    storage = ThreadStorage(persistent)
    create_ops = FilesystemOperationRepository(history / "operations/thread-create-v1")
    status_ops = FilesystemOperationRepository(history / "operations/thread-status-v1")
    delete_ops = FilesystemOperationRepository(history / "operations/thread-delete-v1")
    creation = FilesystemLinkedThreadCreation(
        backend, storage, FilesystemEventRepository(history / "events/thread-create-v1"),
        create_ops, deletion_operations=delete_ops)
    status = FilesystemThreadOperations(
        storage, FilesystemEventRepository(history / "events/thread-status-v1"),
        status_ops, creation_operations=create_ops, deletion_operations=delete_ops)
    deletion = FilesystemThreadDeletion(
        storage, delete_ops, status_operations=status_ops, creation_operations=create_ops)
    return backend, ThreadService(storage, status, creation, deletion), (create_ops, status_ops, delete_ops)


def test_full_recovery_then_unlink_then_information_deletion(tmp_path, monkeypatch):
    backend, service, journals = open_service(tmp_path)
    backend.store(Memory("info-1", content="Retained during Thread work"))
    thread = Thread("thread-1", "Review", "Resolve the fact",
                    created_at="2026-09-30T12:00:00Z", updated_at="2026-09-30T12:00:00Z")
    original_create_event = service.creation.events.save

    def interrupt_creation(event):
        original_create_event(event)
        raise InterruptedError("after creation Event")

    monkeypatch.setattr(service.creation.events, "save", interrupt_creation)
    with pytest.raises(InterruptedError):
        service.create_linked(thread, "info-1", operation_id="create-1", event_id="created-1")
    _, service, journals = open_service(tmp_path)
    assert service.recover_all() == {"creations": {"create-1": {"status": "COMMITTED"}},
                                     "status_changes": {}, "deletions": {}}

    backend.delete_request("info-1", "human", "obsolete", 1, "remove-info-1")
    with pytest.raises(InformationDeletionBlocked):
        backend.approve_delete("info-1", "remove-info-1")

    original_status_event = service.operations.events.save

    def interrupt_status(event):
        original_status_event(event)
        raise InterruptedError("after status Event")

    monkeypatch.setattr(service.operations.events, "save", interrupt_status)
    with pytest.raises(InterruptedError):
        service.change_status("thread-1", ThreadStatus.VALIDATED,
                              previous_revision=1, operation_id="status-1", event_id="status-event-1")
    _, service, journals = open_service(tmp_path)
    assert service.recover_all()["status_changes"] == {"status-1": {"status": "COMMITTED"}}
    assert service.get("thread-1").revision == 2
    assert backend.get("info-1").content == "Retained during Thread work"

    original_unlink = service.storage._delete_committed

    def interrupt_deletion(identity):
        original_unlink(identity)
        raise InterruptedError("after Thread unlink")

    monkeypatch.setattr(service.storage, "_delete_committed", interrupt_deletion)
    with pytest.raises(InterruptedError):
        service.delete("thread-1", previous_revision=2, operation_id="delete-thread-1")
    backend, service, journals = open_service(tmp_path)
    assert service.recover_all()["deletions"] == {"delete-thread-1": {"status": "COMMITTED"}}
    assert service.get("thread-1") is None
    assert all(journal.get(identity).status is OperationStatus.COMMITTED
               for journal, identity in zip(journals, ("create-1", "status-1", "delete-thread-1")))
    assert backend.approve_delete("info-1", "remove-info-1").status == "DELETED"
    assert backend.get("info-1") is None
