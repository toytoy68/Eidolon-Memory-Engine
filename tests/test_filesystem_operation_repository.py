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
)


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
    )

    repository.create(operation)

    loaded = repository.get("op-test-001")

    assert loaded == operation


def test_create_rejects_duplicate_operation_id(tmp_path):
    repository = FilesystemOperationRepository(tmp_path)

    operation = OperationRecord(
        operation_id="op-test-001",
        operation_type=OperationType.THREAD_STATUS_CHANGE,
        target_id="thread-test-001",
        previous_revision=1,
        revision=2,
        execution_plan_hash="sha256-test",
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
    )

    applying = OperationRecord(
        operation_id="op-applying",
        operation_type=OperationType.THREAD_STATUS_CHANGE,
        target_id="thread-002",
        previous_revision=2,
        revision=3,
        execution_plan_hash="hash-applying",
        status=OperationStatus.APPLYING,
    )

    committed = OperationRecord(
        operation_id="op-committed",
        operation_type=OperationType.THREAD_STATUS_CHANGE,
        target_id="thread-003",
        previous_revision=3,
        revision=4,
        execution_plan_hash="hash-committed",
        status=OperationStatus.COMMITTED,
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
    )

    with pytest.raises(ValueError):
        repository.update(backwards)
