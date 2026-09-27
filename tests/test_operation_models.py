import pytest

from core.operations.models import (
    OperationRecord,
    OperationStatus,
    OperationType,
)


def test_create_prepared_thread_status_operation():
    operation = OperationRecord(
        operation_id="op-test-001",
        operation_type=OperationType.THREAD_STATUS_CHANGE,
        target_id="thread-test-001",
        previous_revision=1,
        revision=2,
        execution_plan_hash="sha256-test",
        status=OperationStatus.PREPARED,
    )

    assert operation.operation_id == "op-test-001"
    assert operation.operation_type is OperationType.THREAD_STATUS_CHANGE
    assert operation.target_id == "thread-test-001"
    assert operation.previous_revision == 1
    assert operation.revision == 2
    assert operation.execution_plan_hash == "sha256-test"
    assert operation.status is OperationStatus.PREPARED


def test_operation_rejects_invalid_revision_transition():
    with pytest.raises(ValueError):
        OperationRecord(
            operation_id="op-test-002",
            operation_type=OperationType.THREAD_STATUS_CHANGE,
            target_id="thread-test-001",
            previous_revision=1,
            revision=3,
            execution_plan_hash="sha256-test",
        )


def test_operation_rejects_invalid_status_transition():
    from core.operations.models import validate_status_transition

    with pytest.raises(ValueError):
        validate_status_transition(
            OperationStatus.APPLYING,
            OperationStatus.PREPARED,
        )


@pytest.mark.parametrize(
    ("current", "new"),
    [
        (OperationStatus.PREPARED, OperationStatus.APPLYING),
        (OperationStatus.PREPARED, OperationStatus.FAILED),
        (OperationStatus.APPLYING, OperationStatus.COMMITTED),
        (OperationStatus.APPLYING, OperationStatus.FAILED),
    ],
)
def test_operation_accepts_valid_status_transitions(current, new):
    from core.operations.models import validate_status_transition

    validate_status_transition(current, new)
