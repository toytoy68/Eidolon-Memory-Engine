"""Exercise real repositories together on an isolated memory tree."""

from dataclasses import replace
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.backend.errors import InformationDeletionBlocked
from core.events.filesystem import FilesystemEventRepository
from core.operations.filesystem import FilesystemOperationRepository
from core.operations.models import OperationStatus
from core.operations.errors import OperationConflict
from core.operations.thread_status import FilesystemThreadOperations
from core.operations.thread_create import FilesystemLinkedThreadCreation
from core.threads.link_service import ThreadInformationLinkService
from core.threads.models import Thread, ThreadStatus
from core.threads.storage import ThreadStorage


def open_engine(root):
    persistent = root / "memory" / "persistent"
    history = root / "memory" / "history"
    backend = FilesystemBackend(persistent, history)
    threads = ThreadStorage(persistent)
    operations = FilesystemOperationRepository(history / "operations" / "thread-status-v1")
    events = FilesystemEventRepository(history / "events" / "thread-status-v1")
    creations = FilesystemOperationRepository(history / "operations" / "thread-create-v1")
    return backend, FilesystemThreadOperations(threads, events, operations, creations)


def open_creation(root):
    persistent = root / "memory/persistent"
    history = root / "memory/history"
    backend = FilesystemBackend(persistent, history)
    threads = ThreadStorage(persistent)
    operations = FilesystemOperationRepository(history / "operations/thread-create-v1")
    events = FilesystemEventRepository(history / "events/thread-create-v1")
    return backend, FilesystemLinkedThreadCreation(backend, threads, events, operations)


def crash_creation_worker(root, phase):
    _, creation = open_creation(Path(root))
    if phase == "prepared":
        target, method = creation.operations, "create"
    elif phase in {"applying", "committed"}:
        target, method = creation.operations, "update"
    elif phase == "thread":
        target, method = creation.storage, "create"
    else:
        target, method = creation.events, "save"
    original = getattr(target, method)

    def stop_after_write(*args, **kwargs):
        result = original(*args, **kwargs)
        if target is creation.operations and method == "update":
            expected = (OperationStatus.APPLYING if phase == "applying"
                        else OperationStatus.COMMITTED)
            if args[0].status != expected:
                return result
        os._exit(74)

    setattr(target, method, stop_after_write)
    thread = Thread("thread-1", "Title", "Objective", created_at="2026-09-28",
                    updated_at="2026-09-28")
    creation.create(thread, "info-1", operation_id="create-1", event_id="created-1")


@pytest.mark.parametrize("phase", ["prepared", "applying", "thread", "event", "committed"])
def test_hard_exit_at_each_linked_creation_boundary_recovers(tmp_path, phase):
    backend, _ = open_creation(tmp_path)
    backend.store(Memory("info-1", content="private content"))
    process = multiprocessing.get_context("spawn").Process(
        target=crash_creation_worker, args=(str(tmp_path), phase))
    process.start()
    process.join(timeout=20)
    if process.is_alive():
        process.terminate()
        process.join()
        pytest.fail("creation deadlocked")
    assert process.exitcode == 74
    _, restarted = open_creation(tmp_path)
    assert restarted.recover().get("create-1", {"status": "COMMITTED"})["status"] == "COMMITTED"
    linked = restarted.storage.get("thread-1")
    assert linked.relations == [{"type": "CONCERNS", "target_id": "info-1"}]
    assert restarted.operations.get("create-1").status is OperationStatus.COMMITTED
    assert [event.event_id for event in restarted.events.list_for_target("thread-1")] == ["created-1"]
    assert restarted.backend.get("info-1").content == "private content"
    thread = Thread("thread-1", "Title", "Objective", created_at="2026-09-28",
                    updated_at="2026-09-28")
    assert restarted.create(thread, "info-1", operation_id="create-1", event_id="created-1") == linked
    assert restarted.recover() == {}


def test_information_and_thread_survive_interrupted_status_commit(tmp_path, monkeypatch):
    backend, engine = open_engine(tmp_path)
    original = Memory("info-1", content="A paragraph with **Markdown**.",
                      metadata={"type": "FACT"})
    backend.store(original)
    thread = Thread(
        "thread-1", "Review information", "Validate info-1",
        created_at="2026-09-28T00:00:00+00:00",
        updated_at="2026-09-28T00:00:00+00:00",
    )
    thread = ThreadInformationLinkService(backend, engine.storage).create(thread, "info-1")

    save = engine.events.save

    def interrupt_after_event(event):
        save(event)
        raise InterruptedError("simulated interruption after durable Event write")

    monkeypatch.setattr(engine.events, "save", interrupt_after_event)
    with pytest.raises(InterruptedError):
        engine.change_status("thread-1", ThreadStatus.VALIDATED,
                             previous_revision=1, operation_id="op-1", event_id="event-1")

    backend, restarted = open_engine(tmp_path)
    assert restarted.operations.get("op-1").status is OperationStatus.APPLYING
    assert restarted.recover() == {"op-1": {"status": "COMMITTED"}}
    result = restarted.storage.get("thread-1")
    assert result.status is ThreadStatus.VALIDATED
    assert result.revision == 2
    assert result.relations == thread.relations
    assert backend.get("info-1") == original

    event, = restarted.events.list_for_target("thread-1")
    assert event.event_id == "event-1"
    assert event.revision == result.revision
    assert restarted.operations.get("op-1").status is OperationStatus.COMMITTED
    assert restarted.change_status("thread-1", ThreadStatus.VALIDATED,
                                    previous_revision=1, operation_id="op-1",
                                    event_id="event-1") == result
    assert restarted.recover() == {}
    assert len(restarted.events.list_for_target("thread-1")) == 1


def test_linked_thread_creation_recovers_after_event_write(tmp_path, monkeypatch):
    backend, creation = open_creation(tmp_path)
    backend.store(Memory("info-1", content="private content"))
    thread = Thread("thread-1", "Title", "Objective", created_at="2026-09-28",
                    updated_at="2026-09-28")
    save = creation.events.save

    def interrupt_after_event(event):
        save(event)
        raise InterruptedError("interrupted after Event write")

    monkeypatch.setattr(creation.events, "save", interrupt_after_event)
    with pytest.raises(InterruptedError):
        creation.create(thread, "info-1", operation_id="create-1", event_id="created-1")

    backend, restarted = open_creation(tmp_path)
    assert restarted.operations.get("create-1").status is OperationStatus.APPLYING
    assert restarted.recover() == {"create-1": {"status": "COMMITTED"}}
    linked = restarted.storage.get("thread-1")
    assert linked.relations == [{"type": "CONCERNS", "target_id": "info-1"}]
    assert backend.get("info-1").content == "private content"
    event, = restarted.events.list_for_target("thread-1")
    assert event.event_id == "created-1"
    assert event.state_transition.after == {"status": linked.status.value}
    assert restarted.create(thread, "info-1", operation_id="create-1", event_id="created-1") == linked
    assert restarted.recover() == {}
    assert len(restarted.events.list_for_target("thread-1")) == 1


def test_linked_thread_creation_conflicting_replay_is_blocked(tmp_path):
    backend, creation = open_creation(tmp_path)
    backend.store(Memory("info-1"))
    thread = Thread("thread-1", "Title", "Objective", created_at="2026-09-28",
                    updated_at="2026-09-28")
    creation.create(thread, "info-1", operation_id="create-1", event_id="created-1")
    with pytest.raises(OperationConflict, match="different command"):
        creation.create(thread, "info-1", operation_id="create-1", event_id="created-2")


def test_linked_thread_creation_recovers_after_thread_write(tmp_path, monkeypatch):
    backend, creation = open_creation(tmp_path)
    backend.store(Memory("info-1"))
    thread = Thread("thread-1", "Title", "Objective", created_at="2026-09-28",
                    updated_at="2026-09-28")
    create = creation.storage.create

    def interrupt_after_thread(value):
        create(value)
        raise InterruptedError("interrupted after Thread write")

    monkeypatch.setattr(creation.storage, "create", interrupt_after_thread)
    with pytest.raises(InterruptedError):
        creation.create(thread, "info-1", operation_id="create-1", event_id="created-1")

    _, restarted = open_creation(tmp_path)
    assert restarted.events.get("created-1") is None
    assert restarted.recover() == {"create-1": {"status": "COMMITTED"}}
    assert restarted.events.get("created-1") is not None


def test_linked_thread_creation_recovery_refuses_divergent_thread(tmp_path, monkeypatch):
    backend, creation = open_creation(tmp_path)
    backend.store(Memory("info-1"))
    thread = Thread("thread-1", "Title", "Objective", created_at="2026-09-28",
                    updated_at="2026-09-28")
    create = creation.storage.create

    def interrupt_after_thread(value):
        create(value)
        raise InterruptedError("interrupted after Thread write")

    monkeypatch.setattr(creation.storage, "create", interrupt_after_thread)
    with pytest.raises(InterruptedError):
        creation.create(thread, "info-1", operation_id="create-1", event_id="created-1")

    _, restarted = open_creation(tmp_path)
    path = restarted.storage._path("thread-1")
    path.write_text(restarted.storage._serialize(
        replace(restarted.storage.get("thread-1"), title="different")))
    assert restarted.recover()["create-1"]["status"] == "BLOCKED"
    assert restarted.storage.get("thread-1").title == "different"
    assert restarted.events.get("created-1") is None


def test_create_linked_cli_writes_event_and_replays_idempotently(tmp_path):
    backend, creation = open_creation(tmp_path)
    backend.store(Memory("info-1"))
    command = [
        sys.executable, "-m", "core.operations.cli", "create-linked",
        "thread-1", "info-1", "--title", "Title", "--objective", "Objective",
        "--created-at", "2026-09-28T08:00:00+02:00", "--operation-id", "create-1",
    ]
    environment = {**os.environ, "MEMORY_ENGINE_ROOT": str(tmp_path),
                   "PYTHONDONTWRITEBYTECODE": "1"}
    first = subprocess.run(command, env=environment, capture_output=True, text=True, check=True)
    second = subprocess.run(command, env=environment, capture_output=True, text=True, check=True)

    assert json.loads(first.stdout) == json.loads(second.stdout)
    assert creation.storage.get("thread-1") is not None
    event, = creation.events.list_for_target("thread-1")
    assert event.event_type.value == "CREATED"
    assert creation.operations.get("create-1").status is OperationStatus.COMMITTED


def test_recorded_creation_then_interrupted_status_keeps_both_events(tmp_path, monkeypatch):
    backend, creation = open_creation(tmp_path)
    backend.store(Memory("info-1", content="kept"))
    thread = Thread("thread-1", "Title", "Objective", created_at="2026-09-28",
                    updated_at="2026-09-28")
    created = creation.create(thread, "info-1", operation_id="create-1", event_id="created-1")
    _, status = open_engine(tmp_path)
    save = status.events.save

    def interrupt_after_status_event(event):
        save(event)
        raise InterruptedError("interrupted after status Event")

    monkeypatch.setattr(status.events, "save", interrupt_after_status_event)
    with pytest.raises(InterruptedError):
        status.change_status("thread-1", ThreadStatus.VALIDATED,
                             previous_revision=1, operation_id="status-1", event_id="status-event-1")

    backend, restarted_creation = open_creation(tmp_path)
    _, restarted_status = open_engine(tmp_path)
    assert restarted_creation.recover() == {}
    assert restarted_status.recover() == {"status-1": {"status": "COMMITTED"}}
    updated = restarted_status.storage.get("thread-1")
    assert updated.revision == 2 and updated.status is ThreadStatus.VALIDATED
    assert updated.relations == created.relations
    assert backend.get("info-1").content == "kept"
    creation_event, = restarted_creation.events.list_for_target("thread-1")
    status_event, = restarted_status.events.list_for_target("thread-1")
    assert creation_event.event_type.value == "CREATED"
    assert status_event.event_type.value == "STATUS_CHANGED"
    assert creation_event.relations[0].target == "info-1"


def test_linked_creation_rejects_noninitial_revision_before_journal(tmp_path):
    backend, creation = open_creation(tmp_path)
    backend.store(Memory("info-1"))
    thread = Thread("thread-1", "Title", "Objective", revision=2,
                    created_at="2026-09-28", updated_at="2026-09-28")

    with pytest.raises(OperationConflict, match="revision 1"):
        creation.create(thread, "info-1", operation_id="create-1", event_id="created-1")
    assert creation.storage.get("thread-1") is None
    assert creation.operations.get("create-1") is None


def test_linked_creation_blocks_second_operation_for_pending_thread(tmp_path, monkeypatch):
    backend, creation = open_creation(tmp_path)
    backend.store(Memory("info-1"))
    thread = Thread("thread-1", "Title", "Objective", created_at="2026-09-28",
                    updated_at="2026-09-28")
    save = creation.operations.create

    def interrupt_after_journal(operation):
        save(operation)
        raise InterruptedError("interrupted after journal write")

    monkeypatch.setattr(creation.operations, "create", interrupt_after_journal)
    with pytest.raises(InterruptedError):
        creation.create(thread, "info-1", operation_id="create-1", event_id="created-1")

    _, restarted = open_creation(tmp_path)
    assert restarted.storage.get("thread-1") is None
    with pytest.raises(OperationConflict, match="creation operation"):
        restarted.create(thread, "info-1", operation_id="create-2", event_id="created-2")
    assert restarted.operations.get("create-2") is None
    assert restarted.recover() == {"create-1": {"status": "COMMITTED"}}


def test_pending_thread_creation_reserves_information_until_recovery(tmp_path, monkeypatch):
    backend, creation = open_creation(tmp_path)
    backend.store(Memory("info-1"))
    thread = Thread("thread-1", "Title", "Objective", created_at="2026-09-28",
                    updated_at="2026-09-28")
    save = creation.operations.create

    def interrupt_after_journal(operation):
        save(operation)
        raise InterruptedError("interrupted after journal write")

    monkeypatch.setattr(creation.operations, "create", interrupt_after_journal)
    with pytest.raises(InterruptedError):
        creation.create(thread, "info-1", operation_id="create-1", event_id="created-1")
    assert creation.storage.get("thread-1") is None
    backend.delete_request("info-1", "human", "obsolete", 1, "delete-1")
    with pytest.raises(InformationDeletionBlocked, match="pending Thread creation"):
        backend.approve_delete("info-1", "delete-1")
    assert backend.get("info-1") is not None
    assert creation.recover() == {"create-1": {"status": "COMMITTED"}}
    with pytest.raises(InformationDeletionBlocked, match="linked by Thread"):
        backend.approve_delete("info-1", "delete-1")


def test_unreadable_creation_journal_blocks_information_deletion(tmp_path):
    backend, creation = open_creation(tmp_path)
    backend.store(Memory("info-1"))
    backend.delete_request("info-1", "human", "obsolete", 1, "delete-1")
    (creation.operations.root / "broken.json").write_text("{bad", encoding="utf-8")
    with pytest.raises(InformationDeletionBlocked, match="unreadable Thread creation journal"):
        backend.approve_delete("info-1", "delete-1")
    assert backend.get("info-1") is not None


def test_pending_creation_for_other_information_does_not_block_deletion(tmp_path, monkeypatch):
    backend, creation = open_creation(tmp_path)
    backend.store(Memory("info-1"))
    backend.store(Memory("info-2"))
    thread = Thread("thread-2", "Title", "Objective", created_at="2026-09-28",
                    updated_at="2026-09-28")
    save = creation.operations.create

    def interrupt_after_journal(operation):
        save(operation)
        raise InterruptedError("interrupted after journal write")

    monkeypatch.setattr(creation.operations, "create", interrupt_after_journal)
    with pytest.raises(InterruptedError):
        creation.create(thread, "info-2", operation_id="create-2", event_id="created-2")
    backend.delete_request("info-1", "human", "obsolete", 1, "delete-1")
    assert backend.approve_delete("info-1", "delete-1").status == "DELETED"
    assert backend.get("info-2") is not None


def test_status_change_waits_for_interrupted_thread_creation(tmp_path, monkeypatch):
    backend, creation = open_creation(tmp_path)
    backend.store(Memory("info-1"))
    thread = Thread("thread-1", "Title", "Objective", created_at="2026-09-28",
                    updated_at="2026-09-28")
    create = creation.storage.create

    def interrupt_after_thread(value):
        create(value)
        raise InterruptedError("interrupted after Thread write")

    monkeypatch.setattr(creation.storage, "create", interrupt_after_thread)
    with pytest.raises(InterruptedError):
        creation.create(thread, "info-1", operation_id="create-1", event_id="created-1")

    _, status = open_engine(tmp_path)
    with pytest.raises(OperationConflict, match="recover Thread creation"):
        status.change_status("thread-1", ThreadStatus.VALIDATED,
                             previous_revision=1, operation_id="status-1", event_id="status-event-1")
    assert status.operations.get("status-1") is None
    _, restarted = open_creation(tmp_path)
    assert restarted.recover() == {"create-1": {"status": "COMMITTED"}}
    assert status.change_status("thread-1", ThreadStatus.VALIDATED,
                                previous_revision=1, operation_id="status-1",
                                event_id="status-event-1").status is ThreadStatus.VALIDATED


def test_recover_all_cli_resumes_pending_creation(tmp_path, monkeypatch):
    backend, creation = open_creation(tmp_path)
    backend.store(Memory("info-1"))
    thread = Thread("thread-1", "Title", "Objective", created_at="2026-09-28",
                    updated_at="2026-09-28")
    save = creation.operations.create

    def interrupt_after_journal(operation):
        save(operation)
        raise InterruptedError("interrupted after journal write")

    monkeypatch.setattr(creation.operations, "create", interrupt_after_journal)
    with pytest.raises(InterruptedError):
        creation.create(thread, "info-1", operation_id="create-1", event_id="created-1")

    result = subprocess.run(
        [sys.executable, "-m", "core.operations.cli", "recover-all"],
        env={**os.environ, "MEMORY_ENGINE_ROOT": str(tmp_path), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, text=True, check=True,
    )
    assert json.loads(result.stdout) == {
        "creations": {"create-1": {"status": "COMMITTED"}}, "status_changes": {},
    }
    _, restarted = open_creation(tmp_path)
    assert restarted.storage.get("thread-1") is not None
    assert restarted.events.get("created-1") is not None


def test_recover_all_cli_reports_blocked_creation_without_overwrite(tmp_path, monkeypatch):
    backend, creation = open_creation(tmp_path)
    backend.store(Memory("info-1"))
    thread = Thread("thread-1", "Title", "Objective", created_at="2026-09-28",
                    updated_at="2026-09-28")
    create = creation.storage.create

    def interrupt_after_thread(value):
        create(value)
        raise InterruptedError("interrupted after Thread write")

    monkeypatch.setattr(creation.storage, "create", interrupt_after_thread)
    with pytest.raises(InterruptedError):
        creation.create(thread, "info-1", operation_id="create-1", event_id="created-1")
    path = creation.storage._path("thread-1")
    path.write_text(creation.storage._serialize(replace(creation.storage.get("thread-1"),
                                                     title="changed externally")))
    before = path.read_bytes()

    result = subprocess.run(
        [sys.executable, "-m", "core.operations.cli", "recover-all"],
        env={**os.environ, "MEMORY_ENGINE_ROOT": str(tmp_path), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["creations"]["create-1"]["status"] == "BLOCKED"
    assert report["status_changes"] == {}
    assert path.read_bytes() == before
    assert creation.events.get("created-1") is None
