import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from core.operations.errors import OperationConflict
from core.operations.filesystem import FilesystemOperationRepository
from core.operations.models import OperationStatus
from core.operations.thread_delete import FilesystemThreadDeletion
from core.operations.thread_status import FilesystemThreadOperations
from core.events.filesystem import FilesystemEventRepository
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.operations.thread_create import FilesystemLinkedThreadCreation
from core.threads.models import ThreadStatus
from core.threads.models import Thread
from core.threads.storage import ThreadStorage, ThreadStorageError
from core.threads.service import ThreadService


def setup(root):
    storage = ThreadStorage(root / "memory/persistent")
    operations = FilesystemOperationRepository(root / "memory/history/operations/thread-delete-v1")
    deletion = FilesystemThreadDeletion(storage, operations)
    storage.create(Thread("thread-1", "Title", "Objective", created_at="2026-09-30",
                          updated_at="2026-09-30"))
    return storage, operations, deletion


def test_storage_delete_is_journaled_and_replayable(tmp_path):
    storage, operations, deletion = setup(tmp_path)
    with pytest.raises(ThreadStorageError, match="operation_id"):
        storage.delete("thread-1")
    storage.delete("thread-1", previous_revision=1, operation_id="op-1", coordinator=deletion)
    assert storage.get("thread-1") is None
    assert operations.get("op-1").status is OperationStatus.COMMITTED
    storage.delete("thread-1", previous_revision=1, operation_id="op-1", coordinator=deletion)
    with pytest.raises(OperationConflict):
        deletion.delete("thread-1", previous_revision=2, operation_id="op-1")


def test_service_exposes_journaled_delete_and_recovery(tmp_path):
    storage, operations, deletion = setup(tmp_path)
    service = ThreadService(storage, deletion=deletion)
    service.delete("thread-1", previous_revision=1, operation_id="service-delete")
    assert storage.get("thread-1") is None
    assert operations.get("service-delete").status is OperationStatus.COMMITTED


@pytest.mark.parametrize("boundary", ["applying", "unlinked"])
def test_thread_deletion_recovers_after_interruption(tmp_path, monkeypatch, boundary):
    storage, operations, deletion = setup(tmp_path)
    if boundary == "applying":
        original = storage._delete_committed

        def interrupted(thread_id):
            raise RuntimeError("simulated process exit before unlink")

        monkeypatch.setattr(storage, "_delete_committed", interrupted)
    else:
        original = storage._delete_committed

        def interrupted(thread_id):
            original(thread_id)
            raise RuntimeError("simulated process exit after unlink")

        monkeypatch.setattr(storage, "_delete_committed", interrupted)
    with pytest.raises(RuntimeError, match="simulated process exit"):
        deletion.delete("thread-1", previous_revision=1, operation_id="op-1")
    assert operations.get("op-1").status is OperationStatus.APPLYING
    monkeypatch.setattr(storage, "_delete_committed", original)

    restarted = FilesystemThreadDeletion(storage, operations)
    assert restarted.recover() == {"op-1": {"status": "COMMITTED"}}
    assert storage.get("thread-1") is None
    assert operations.get("op-1").status is OperationStatus.COMMITTED


def test_thread_deletion_never_removes_divergent_replacement(tmp_path, monkeypatch):
    storage, operations, deletion = setup(tmp_path)
    original = storage._delete_committed

    def interrupted(thread_id):
        original(thread_id)
        raise RuntimeError("interrupt")

    monkeypatch.setattr(storage, "_delete_committed", interrupted)
    with pytest.raises(RuntimeError):
        deletion.delete("thread-1", previous_revision=1, operation_id="op-1")
    monkeypatch.setattr(storage, "_delete_committed", original)
    storage.create(Thread("thread-1", "Replacement", "Objective", created_at="2026-09-30",
                          updated_at="2026-09-30"))
    report = deletion.recover()
    assert report["op-1"]["status"] == "BLOCKED"
    assert storage.get("thread-1").title == "Replacement"


def test_delete_cli_and_recover_all_expose_deletion(tmp_path):
    storage, operations, deletion = setup(tmp_path)
    env = dict(os.environ, MEMORY_ENGINE_ROOT=str(tmp_path), PYTHONDONTWRITEBYTECODE="1")
    command = [sys.executable, "-m", "core.operations.cli", "delete-thread", "thread-1",
               "--previous-revision", "1", "--operation-id", "op-1"]
    result = subprocess.run(command, capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    assert storage.get("thread-1") is None
    assert operations.get("op-1").status is OperationStatus.COMMITTED
    recovered = subprocess.run([sys.executable, "-m", "core.operations.cli", "recover-all"],
                               capture_output=True, text=True, env=env, check=True)
    assert "deletions" in json.loads(recovered.stdout)


@pytest.mark.parametrize("boundary", ["before_unlink", "after_unlink"])
def test_hard_process_exit_during_thread_deletion_recovers(tmp_path, boundary):
    storage, operations, _ = setup(tmp_path)
    child = """
import os, sys
from pathlib import Path
from core.threads.storage import ThreadStorage
from core.operations.filesystem import FilesystemOperationRepository
from core.operations.thread_delete import FilesystemThreadDeletion
root = Path(sys.argv[1])
storage = ThreadStorage(root / 'memory/persistent')
operations = FilesystemOperationRepository(root / 'memory/history/operations/thread-delete-v1')
original = storage._delete_committed
def cut(thread_id):
    if sys.argv[2] == 'after_unlink':
        original(thread_id)
    os._exit(47)
storage._delete_committed = cut
FilesystemThreadDeletion(storage, operations).delete(
    'thread-1', previous_revision=1, operation_id='hard-exit')
"""
    result = subprocess.run([sys.executable, "-c", child, str(tmp_path), boundary],
                            cwd=Path(__file__).resolve().parents[1],
                            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 47, result.stderr
    assert operations.get("hard-exit").status is OperationStatus.APPLYING
    assert FilesystemThreadDeletion(storage, operations).recover() == {
        "hard-exit": {"status": "COMMITTED"}}
    assert storage.get("thread-1") is None


def test_status_change_waits_for_pending_deletion(tmp_path, monkeypatch):
    storage, deletions, deletion = setup(tmp_path)
    monkeypatch.setattr(storage, "_delete_committed", lambda thread_id: (_ for _ in ()).throw(
        RuntimeError("interrupted")))
    with pytest.raises(RuntimeError):
        deletion.delete("thread-1", previous_revision=1, operation_id="pending-delete")
    statuses = FilesystemThreadOperations(
        storage, FilesystemEventRepository(tmp_path / "memory/history/events/thread-status-v1"),
        FilesystemOperationRepository(tmp_path / "memory/history/operations/thread-status-v1"),
        deletion_operations=deletions)
    with pytest.raises(OperationConflict, match="deletion"):
        statuses.change_status("thread-1", ThreadStatus.VALIDATED,
                               previous_revision=1, operation_id="status-after-delete",
                               event_id="event-after-delete")
    assert storage.get("thread-1").revision == 1


def test_linked_creation_waits_for_pending_deletion(tmp_path, monkeypatch):
    storage, deletions, deletion = setup(tmp_path)
    original = storage._delete_committed

    def interrupted(thread_id):
        original(thread_id)
        raise RuntimeError("interrupted")

    monkeypatch.setattr(storage, "_delete_committed", interrupted)
    with pytest.raises(RuntimeError):
        deletion.delete("thread-1", previous_revision=1, operation_id="pending-delete")
    backend = FilesystemBackend(tmp_path / "memory/persistent", tmp_path / "memory/history")
    backend.store(Memory("info-1"))
    creation = FilesystemLinkedThreadCreation(
        backend, storage,
        FilesystemEventRepository(tmp_path / "memory/history/events/thread-create-v1"),
        FilesystemOperationRepository(tmp_path / "memory/history/operations/thread-create-v1"),
        deletion_operations=deletions)
    with pytest.raises(OperationConflict, match="deletion"):
        creation.create(Thread("thread-1", "Replacement", "Objective",
                               created_at="2026-09-30", updated_at="2026-09-30"), "info-1",
                        operation_id="new-create", event_id="new-event")
    assert storage.get("thread-1") is None
