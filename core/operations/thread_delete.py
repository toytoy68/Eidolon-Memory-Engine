"""Journaled, repeatable deletion of a persisted Thread snapshot."""

from __future__ import annotations

from dataclasses import replace

from core.operations.errors import OperationConflict, OperationNotFound, OperationRepositoryError
from core.operations.filesystem import FilesystemOperationRepository
from core.operations.models import OperationRecord, OperationStatus, OperationType, ThreadDeletePlan
from core.operations.thread_status import plan_hash
from core.persistence import exclusive_write
from core.threads.storage import ThreadStorage, ThreadStorageError, ThreadRevisionConflict


class FilesystemThreadDeletion:
    def __init__(self, storage: ThreadStorage, operations: FilesystemOperationRepository,
                 *, status_operations: FilesystemOperationRepository | None = None,
                 creation_operations: FilesystemOperationRepository | None = None):
        self.storage = storage
        self.operations = operations
        self.status_operations = status_operations
        self.creation_operations = creation_operations

    def delete(self, thread_id: str, *, previous_revision: int, operation_id: str) -> None:
        self.storage._path(thread_id)
        self.operations._path(operation_id)
        with exclusive_write(self.storage.threads_root):
            for other in (self.status_operations, self.creation_operations):
                if other is not None:
                    if other.get(operation_id) is not None or any(
                        pending.target_id == thread_id for pending in other.list_incomplete()
                    ):
                        raise OperationConflict("recover other Thread operation before deletion")
            existing = self.operations.get(operation_id)
            if existing is not None:
                if (existing.operation_type is not OperationType.THREAD_DELETE
                        or existing.target_id != thread_id
                        or existing.previous_revision != previous_revision):
                    raise OperationConflict("operation_id reused for a different deletion")
                self._resume(existing)
                return
            if any(pending.target_id == thread_id for pending in self.operations.list_incomplete()):
                raise OperationConflict("recover pending Thread deletion first")
            before = self.storage.get(thread_id)
            if before is None:
                raise ThreadStorageError(f"Thread not found: {thread_id}")
            if before.revision != previous_revision:
                raise ThreadRevisionConflict("Thread revision changed before deletion")
            snapshot = self.storage._serialize_checked(before)
            operation = OperationRecord(
                operation_id, OperationType.THREAD_DELETE, thread_id,
                previous_revision, previous_revision + 1, "",
                plan=ThreadDeletePlan(snapshot),
            )
            operation = replace(operation, execution_plan_hash=plan_hash(operation))
            self.operations.create(operation)
            self._resume(operation)

    def _resume(self, operation: OperationRecord) -> None:
        if (operation.operation_type is not OperationType.THREAD_DELETE
                or not isinstance(operation.plan, ThreadDeletePlan)
                or plan_hash(operation) != operation.execution_plan_hash):
            raise OperationConflict("invalid Thread deletion plan")
        before = self.storage._deserialize(operation.plan.before_state)
        if (before.thread_id != operation.target_id
                or before.revision != operation.previous_revision
                or operation.revision != before.revision + 1):
            raise OperationConflict("Thread deletion snapshot identity mismatch")
        current = self.storage.get(operation.target_id)
        if current is not None and current != before:
            raise OperationConflict("Thread diverged from deletion snapshot")
        if operation.status is OperationStatus.COMMITTED:
            if current is not None:
                raise OperationConflict("deleted Thread identity was reused")
            return
        if operation.status is OperationStatus.FAILED:
            raise OperationConflict("failed deletion requires manual review")
        for other in (self.status_operations, self.creation_operations):
            if other is not None and any(
                pending.target_id == operation.target_id for pending in other.list_incomplete()
            ):
                raise OperationConflict("recover other Thread operation before deletion")
        if current is None and operation.status is OperationStatus.PREPARED:
            raise OperationConflict("Thread missing before deletion began")
        if operation.status is OperationStatus.PREPARED:
            operation = replace(operation, status=OperationStatus.APPLYING)
            self.operations.update(operation)
        if current is not None:
            self.storage._delete_committed(operation.target_id)
        self.operations.update(replace(operation, status=OperationStatus.COMMITTED))

    def resume(self, operation_id: str) -> None:
        with exclusive_write(self.storage.threads_root):
            operation = self.operations.get(operation_id)
            if operation is None:
                raise OperationNotFound(operation_id)
            self._resume(operation)

    def recover(self) -> dict[str, dict[str, str]]:
        result = {}
        for path in sorted(self.operations.root.glob("*.json")):
            try:
                with exclusive_write(self.storage.threads_root):
                    operation = self.operations.get(path.stem)
                    if operation is None or operation.status in {
                        OperationStatus.COMMITTED, OperationStatus.FAILED,
                    }:
                        continue
                    self._resume(operation)
                result[path.stem] = {"status": "COMMITTED"}
            except (OSError, ValueError, TypeError, OperationRepositoryError,
                    ThreadStorageError) as exc:
                result[path.stem] = {"status": "BLOCKED", "error": type(exc).__name__}
        return result
