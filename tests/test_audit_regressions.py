"""Regression tests for the b25da00 audit; all persistence uses tmp_path."""
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
import multiprocessing
from pathlib import Path

import pytest

from core.backend.errors import RevisionConflict, InvalidMemory
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.events.errors import InvalidEvent, EventAlreadyExists
from core.events.filesystem import FilesystemEventRepository
from core.events.models import Event, EventType
from core.operations.errors import InvalidOperationRecord, OperationConflict, OperationAlreadyExists
from core.operations.filesystem import FilesystemOperationRepository
from core.operations.models import (
    OperationRecord, OperationType, OperationStatus, ThreadStatusChangePlan,
)
from core.threads.manager import ThreadManager
from core.threads.models import Thread, ThreadAction, ThreadStatus
from core.threads.queries import ThreadQuery, ThreadQueryType
from core.threads.storage import ThreadStorage, ThreadRevisionConflict, ThreadStorageError


@pytest.mark.parametrize("repository,error", [
    ("thread", ThreadStorageError), ("information", InvalidMemory),
    ("event", InvalidEvent), ("operation", InvalidOperationRecord),
])
def test_repository_constructor_rejects_linked_parent_before_creation(tmp_path,
                                                                      repository, error):
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "linked").symlink_to(outside, target_is_directory=True)
    target = tmp_path / "linked" / repository
    with pytest.raises(error, match="symlink"):
        if repository == "thread":
            ThreadStorage(target)
        elif repository == "information":
            FilesystemBackend(target, tmp_path / "history")
        elif repository == "event":
            FilesystemEventRepository(target)
        else:
            FilesystemOperationRepository(target)
    assert not (outside / repository).exists()


def operation():
    return OperationRecord("op", OperationType.THREAD_STATUS_CHANGE, "t", 1, 2,
                           "hash", plan=ThreadStatusChangePlan(ThreadStatus.VALIDATED, "e"))


def test_operation_plan_cannot_change_with_same_hash(tmp_path):
    repo = FilesystemOperationRepository(tmp_path)
    original = operation()
    repo.create(original)
    with pytest.raises(OperationConflict):
        repo.update(replace(original, status=OperationStatus.APPLYING,
                            plan=ThreadStatusChangePlan(ThreadStatus.CANCELLED, "other")))
    assert repo.get("op") == original


@pytest.mark.parametrize("identifier", ["../escape", "a/b", "a\\b", "", "/absolute", None])
def test_operation_ids_are_confined(tmp_path, identifier):
    repo = FilesystemOperationRepository(tmp_path / "operations")
    for action in (lambda: repo.create(replace(operation(), operation_id=identifier)),
                   lambda: repo.get(identifier),
                   lambda: repo.update(replace(operation(), operation_id=identifier))):
        with pytest.raises(InvalidOperationRecord):
            action()
    assert not (tmp_path / "escape.json").exists()


@pytest.mark.parametrize("payload", ["[]", "null", "42", '"text"'])
def test_non_object_operation_has_domain_error(tmp_path, payload):
    repo = FilesystemOperationRepository(tmp_path)
    (tmp_path / "bad.json").write_text(payload)
    with pytest.raises(InvalidOperationRecord):
        repo.get("bad")


def backend(root):
    return FilesystemBackend(root / "persistent", root / "history")


def test_cancelled_deletion_cannot_be_approved(tmp_path):
    store = backend(tmp_path)
    store.store(Memory("i", content="original"))
    store.delete_request("i", "user", "reason", 1, "delete")
    store.cancel_delete("i", "delete")
    with pytest.raises(RevisionConflict):
        store.approve_delete("i", "delete")
    assert store.get("i").content == "original"


def test_deletion_cannot_remove_newer_revision(tmp_path):
    store = backend(tmp_path)
    store.store(Memory("i", content="original"))
    store.delete_request("i", "user", "reason", 1, "delete")
    store.update("i", Memory("i", content="new"), 1)
    with pytest.raises(RevisionConflict):
        store.approve_delete("i", "delete")
    assert store.get("i").revision == 2


def test_pending_deletion_can_be_approved_but_not_cancelled_afterwards(tmp_path):
    store = backend(tmp_path)
    store.store(Memory("i", content="original"))
    store.delete_request("i", "user", "reason", 1, "delete")
    assert store.approve_delete("i", "delete").status == "DELETED"
    assert store.get("i") is None
    with pytest.raises(RevisionConflict):
        store.cancel_delete("i", "delete")


@pytest.mark.parametrize("filters", [{"information_id": "i"}, {"revision": 1},
                                      {"information_id": "i", "revision": 1, "type": "FACT"}])
def test_reserved_backend_filters_match(tmp_path, filters):
    store = backend(tmp_path)
    store.store(Memory("i", content="x", metadata={"type": "FACT"}))
    assert [m.information_id for m in store.list(filters=filters)] == ["i"]
    assert store.list(filters={"revision": 2}) == []


def test_action_query_is_scoped_to_requested_thread():
    threads = [Thread(name, name, "objective", actions=[ThreadAction("same", name)])
               for name in ("a", "b")]
    query = ThreadQuery(ThreadQueryType.LIST_THREAD_ACTIONS, thread_id="a", action_id="same")
    assert [t.thread_id for t, _ in ThreadManager.query(threads, query)] == ["a"]


def test_invalid_status_event_is_not_persisted(tmp_path):
    repo = FilesystemEventRepository(tmp_path)
    with pytest.raises(InvalidEvent):
        repo.save(Event("e", 2, EventType.STATUS_CHANGED, thread_id="t"))
    assert repo.get("e") is None


def test_event_identity_matches_filename(tmp_path):
    repo = FilesystemEventRepository(tmp_path)
    repo.save(Event("e", 1, EventType.CREATED, information_id="i"))
    (tmp_path / "renamed.md").write_text((tmp_path / "e.md").read_text())
    with pytest.raises(InvalidEvent):
        repo.get("renamed")
    with pytest.raises(InvalidEvent):
        repo.list_for_target("i")


def competing_writer(root, barrier, kind, number):
    root = Path(root)
    if kind == "thread":
        store = ThreadStorage(root)
        value = replace(store.get("t"), title=str(number), revision=2)
        barrier.wait(timeout=15)
        try:
            store.update(value, 1)
        except ThreadRevisionConflict:
            return "conflict"
    elif kind == "backend":
        store = backend(root)
        barrier.wait(timeout=15)
        try:
            store.update("i", Memory("i", content=str(number)), 1)
        except RevisionConflict:
            return "conflict"
    elif kind == "operation":
        store = FilesystemOperationRepository(root / "operations")
        barrier.wait(timeout=15)
        try:
            store.create(replace(operation(), target_id=str(number)))
        except OperationAlreadyExists:
            return "conflict"
    else:
        store = FilesystemEventRepository(root / "events")
        barrier.wait(timeout=15)
        try:
            store.save(Event("e", 1, EventType.CREATED, information_id=str(number)))
        except EventAlreadyExists:
            return "conflict"
    return "written"


@pytest.mark.parametrize("kind", ["thread", "backend", "event", "operation"])
def test_concurrent_processes_allow_exactly_one_writer(tmp_path, kind):
    if kind == "thread":
        ThreadStorage(tmp_path).create(Thread("t", "original", "objective"))
    elif kind == "backend":
        backend(tmp_path).store(Memory("i", content="original"))
    context = multiprocessing.get_context("spawn")
    with context.Manager() as manager:
        barrier = manager.Barrier(2)
        with ProcessPoolExecutor(2, mp_context=context) as pool:
            futures = [pool.submit(competing_writer, str(tmp_path), barrier, kind, i)
                       for i in range(2)]
            results = [future.result(timeout=30) for future in futures]
    assert sorted(results) == ["conflict", "written"]
