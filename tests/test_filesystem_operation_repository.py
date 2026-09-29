import json

import pytest

from core.operations.errors import (
    InvalidOperationRecord,
    OperationAlreadyExists,
    OperationConflict,
    OperationNotFound,
)
from core.operations.filesystem import FilesystemOperationRepository
from core.operations.models import (
    OperationRecord,
    OperationStatus,
    OperationType,
    ThreadStatusChangePlan,
)
from core.threads.models import ThreadStatus


def test_operation_repository_rejects_symlinked_paths(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "operations"
    root.symlink_to(outside, target_is_directory=True)
    with pytest.raises(InvalidOperationRecord, match="directory is a symlink"):
        FilesystemOperationRepository(root)
    root.unlink()
    repository = FilesystemOperationRepository(root)
    (root / "op-test.json").symlink_to(root / "missing.json")
    with pytest.raises(InvalidOperationRecord, match="symlink"):
        repository.get("op-test")
    operation = OperationRecord(
        operation_id="op-test", operation_type=OperationType.THREAD_STATUS_CHANGE,
        target_id="thread-test", previous_revision=1, revision=2,
        execution_plan_hash="hash",
        plan=ThreadStatusChangePlan(new_status=ThreadStatus.IMPLEMENTATION, event_id="event-test"),
    )
    with pytest.raises(OperationAlreadyExists):
        repository.create(operation)


@pytest.mark.parametrize("location", ["record", "plan"])
def test_operation_rejects_unknown_fields_before_update(tmp_path, location):
    repository = FilesystemOperationRepository(tmp_path)
    operation = OperationRecord(
        operation_id="op-test", operation_type=OperationType.THREAD_STATUS_CHANGE,
        target_id="thread-test", previous_revision=1, revision=2,
        execution_plan_hash="hash",
        plan=ThreadStatusChangePlan(new_status=ThreadStatus.IMPLEMENTATION, event_id="event-test"),
    )
    repository.create(operation)
    path = tmp_path / "op-test.json"
    record = json.loads(path.read_text())
    if location == "record":
        record["private_extension"] = "must not disappear"
    else:
        record["plan"]["private_extension"] = "must not disappear"
    path.write_text(json.dumps(record))
    original = path.read_bytes()
    with pytest.raises(InvalidOperationRecord, match="unknown Operation"):
        repository.get("op-test")
    with pytest.raises(InvalidOperationRecord, match="unknown Operation"):
        repository.update(OperationRecord(
            operation_id="op-test", operation_type=OperationType.THREAD_STATUS_CHANGE,
            target_id="thread-test", previous_revision=1, revision=2,
            execution_plan_hash="hash", status=OperationStatus.APPLYING,
            plan=operation.plan,
        ))
    assert path.read_bytes() == original


@pytest.mark.parametrize("content", [
    '{"operation_id":"op","operation_id":"other"}',
    '{"operation_id":"op","plan":{"event_id":"a","event_id":"b"}}',
    '{"operation_id":"op","revision":NaN}',
])
def test_operation_reader_rejects_ambiguous_json(tmp_path, content):
    repository = FilesystemOperationRepository(tmp_path)
    path = tmp_path / "op.json"
    path.write_text(content)
    with pytest.raises(InvalidOperationRecord):
        repository.get("op")
    assert path.read_text() == content


def test_create_and_get_operation(tmp_path):
    repository = FilesystemOperationRepository(tmp_path)

    operation = OperationRecord(
        operation_id="op-test-001",
        operation_type=OperationType.THREAD_STATUS_CHANGE,
        target_id="thread-test-001",
        previous_revision=1,
        revision=2,
        execution_plan_hash="sha256-test",
        status=OperationStatus.PREPARED,
        plan=ThreadStatusChangePlan(
            new_status=ThreadStatus.IMPLEMENTATION,
            event_id="event-test-001",
        ),
    )

    repository.create(operation)

    loaded = repository.get("op-test-001")

    assert loaded == operation
    assert loaded.plan is not None
    assert loaded.plan.new_status is ThreadStatus.IMPLEMENTATION
    assert loaded.plan.event_id == "event-test-001"


def test_create_rejects_duplicate_operation_id(tmp_path):
    repository = FilesystemOperationRepository(tmp_path)

    operation = OperationRecord(
        operation_id="op-test-001",
        operation_type=OperationType.THREAD_STATUS_CHANGE,
        target_id="thread-test-001",
        previous_revision=1,
        revision=2,
        execution_plan_hash="sha256-test",
        plan=ThreadStatusChangePlan(
            new_status=ThreadStatus.IMPLEMENTATION,
            event_id="event-test-001",
        ),
    )

    repository.create(operation)

    with pytest.raises(OperationAlreadyExists):
        repository.create(operation)


def test_get_returns_none_for_missing_operation(tmp_path):
    repository = FilesystemOperationRepository(tmp_path)

    assert repository.get("op-does-not-exist") is None


def test_update_existing_operation(tmp_path):
    repository = FilesystemOperationRepository(tmp_path)

    operation = OperationRecord(
        operation_id="op-test-001",
        operation_type=OperationType.THREAD_STATUS_CHANGE,
        target_id="thread-test-001",
        previous_revision=1,
        revision=2,
        execution_plan_hash="sha256-test",
        status=OperationStatus.PREPARED,
        plan=ThreadStatusChangePlan(
            new_status=ThreadStatus.IMPLEMENTATION,
            event_id="event-test-001",
        ),
    )

    repository.create(operation)

    updated = OperationRecord(
        operation_id=operation.operation_id,
        operation_type=operation.operation_type,
        target_id=operation.target_id,
        previous_revision=operation.previous_revision,
        revision=operation.revision,
        execution_plan_hash=operation.execution_plan_hash,
        status=OperationStatus.APPLYING,
        plan=ThreadStatusChangePlan(
            new_status=ThreadStatus.IMPLEMENTATION,
            event_id="event-test-001",
        ),
    )

    repository.update(updated)

    assert repository.get("op-test-001") == updated


def test_update_rejects_missing_operation(tmp_path):
    repository = FilesystemOperationRepository(tmp_path)

    operation = OperationRecord(
        operation_id="op-missing",
        operation_type=OperationType.THREAD_STATUS_CHANGE,
        target_id="thread-test-001",
        previous_revision=1,
        revision=2,
        execution_plan_hash="sha256-test",
        status=OperationStatus.APPLYING,
        plan=ThreadStatusChangePlan(
            new_status=ThreadStatus.IMPLEMENTATION,
            event_id="event-test-001",
        ),
    )

    with pytest.raises(OperationNotFound):
        repository.update(operation)


def test_list_incomplete_excludes_committed_operations(tmp_path):
    repository = FilesystemOperationRepository(tmp_path)

    prepared = OperationRecord(
        operation_id="op-prepared",
        operation_type=OperationType.THREAD_STATUS_CHANGE,
        target_id="thread-001",
        previous_revision=1,
        revision=2,
        execution_plan_hash="hash-prepared",
        status=OperationStatus.PREPARED,
        plan=ThreadStatusChangePlan(
            new_status=ThreadStatus.IMPLEMENTATION,
            event_id="event-test-001",
        ),
    )

    applying = OperationRecord(
        operation_id="op-applying",
        operation_type=OperationType.THREAD_STATUS_CHANGE,
        target_id="thread-002",
        previous_revision=2,
        revision=3,
        execution_plan_hash="hash-applying",
        status=OperationStatus.APPLYING,
        plan=ThreadStatusChangePlan(
            new_status=ThreadStatus.IMPLEMENTATION,
            event_id="event-test-001",
        ),
    )

    committed = OperationRecord(
        operation_id="op-committed",
        operation_type=OperationType.THREAD_STATUS_CHANGE,
        target_id="thread-003",
        previous_revision=3,
        revision=4,
        execution_plan_hash="hash-committed",
        status=OperationStatus.COMMITTED,
        plan=ThreadStatusChangePlan(
            new_status=ThreadStatus.IMPLEMENTATION,
            event_id="event-test-001",
        ),
    )

    repository.create(prepared)
    repository.create(applying)
    repository.create(committed)

    incomplete = repository.list_incomplete()

    assert set(operation.operation_id for operation in incomplete) == {
        "op-prepared",
        "op-applying",
    }


def test_get_rejects_corrupted_operation_record(tmp_path):
    repository = FilesystemOperationRepository(tmp_path)

    path = tmp_path / "op-corrupted.json"
    path.write_text("{this is not valid json", encoding="utf-8")

    with pytest.raises(InvalidOperationRecord):
        repository.get("op-corrupted")


def test_get_rejects_mismatched_operation_id(tmp_path):
    repository = FilesystemOperationRepository(tmp_path)

    path = tmp_path / "op-expected.json"
    path.write_text(
        json.dumps(
            {
                "operation_id": "op-other",
                "operation_type": "THREAD_STATUS_CHANGE",
                "target_id": "thread-001",
                "previous_revision": 1,
                "revision": 2,
                "execution_plan_hash": "sha256-test",
                "status": "PREPARED",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(InvalidOperationRecord):
        repository.get("op-expected")


def test_update_rejects_changed_execution_plan(tmp_path):
    repository = FilesystemOperationRepository(tmp_path)

    original = OperationRecord(
        operation_id="op-test-001",
        operation_type=OperationType.THREAD_STATUS_CHANGE,
        target_id="thread-test-001",
        previous_revision=1,
        revision=2,
        execution_plan_hash="hash-original",
        status=OperationStatus.PREPARED,
        plan=ThreadStatusChangePlan(
            new_status=ThreadStatus.IMPLEMENTATION,
            event_id="event-test-001",
        ),
    )

    repository.create(original)

    modified = OperationRecord(
        operation_id=original.operation_id,
        operation_type=original.operation_type,
        target_id=original.target_id,
        previous_revision=original.previous_revision,
        revision=original.revision,
        execution_plan_hash="hash-modified",
        status=OperationStatus.APPLYING,
        plan=ThreadStatusChangePlan(
            new_status=ThreadStatus.IMPLEMENTATION,
            event_id="event-test-001",
        ),
    )

    with pytest.raises(OperationConflict):
        repository.update(modified)


def test_update_rejects_invalid_status_transition(tmp_path):
    repository = FilesystemOperationRepository(tmp_path)

    prepared = OperationRecord(
        operation_id="op-test-001",
        operation_type=OperationType.THREAD_STATUS_CHANGE,
        target_id="thread-test-001",
        previous_revision=1,
        revision=2,
        execution_plan_hash="sha256-test",
        status=OperationStatus.PREPARED,
        plan=ThreadStatusChangePlan(
            new_status=ThreadStatus.IMPLEMENTATION,
            event_id="event-test-001",
        ),
    )
    repository.create(prepared)

    applying = OperationRecord(
        operation_id=prepared.operation_id,
        operation_type=prepared.operation_type,
        target_id=prepared.target_id,
        previous_revision=prepared.previous_revision,
        revision=prepared.revision,
        execution_plan_hash=prepared.execution_plan_hash,
        status=OperationStatus.APPLYING,
        plan=ThreadStatusChangePlan(
            new_status=ThreadStatus.IMPLEMENTATION,
            event_id="event-test-001",
        ),
    )
    repository.update(applying)

    backwards = OperationRecord(
        operation_id=applying.operation_id,
        operation_type=applying.operation_type,
        target_id=applying.target_id,
        previous_revision=applying.previous_revision,
        revision=applying.revision,
        execution_plan_hash=applying.execution_plan_hash,
        status=OperationStatus.PREPARED,
        plan=ThreadStatusChangePlan(
            new_status=ThreadStatus.IMPLEMENTATION,
            event_id="event-test-001",
        ),
    )

    with pytest.raises(ValueError):
        repository.update(backwards)
