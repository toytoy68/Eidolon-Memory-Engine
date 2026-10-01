"""Recoverable filesystem Thread status changes.

Writers hold the Thread storage lock across preparation and commit. Recovery is
roll-forward and fails closed on divergent state; it never overwrites a conflict.
Readers may observe an APPLYING state until recovery completes.
"""
from dataclasses import asdict, replace
import hashlib
import json

from core.events.filesystem import FilesystemEventRepository
from core.events.models import (
    Event, EventType, StateTransition, Provenance, EventRelation, RelationType,
)
from core.operations.errors import OperationConflict, OperationNotFound, OperationRepositoryError
from core.events.errors import EventRepositoryError
from core.operations.filesystem import FilesystemOperationRepository
from core.operations.models import (
    OperationRecord, OperationType, OperationStatus, ThreadStatusChangePlan,
)
from core.persistence import exclusive_write
from core.threads.manager import ThreadManager, ThreadError
from core.threads.models import Thread, ThreadStatus
from core.threads.storage import ThreadStorage, ThreadRevisionConflict, ThreadStorageError


def plan_hash(operation: OperationRecord) -> str:
    payload = asdict(operation)
    payload.pop("status")
    payload.pop("execution_plan_hash")
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


class FilesystemThreadOperations:
    def __init__(self, storage: ThreadStorage, events: FilesystemEventRepository,
                 operations: FilesystemOperationRepository,
                 creation_operations: FilesystemOperationRepository | None = None,
                 deletion_operations: FilesystemOperationRepository | None = None):
        self.storage = storage
        self.events = events
        self.operations = operations
        self.creation_operations = creation_operations
        self.deletion_operations = deletion_operations

    def change_status(self, thread_id: str, new_status: ThreadStatus, *,
                      previous_revision: int, operation_id: str, event_id: str) -> Thread:
        # Validate paths before any record is written.
        self.storage._path(thread_id)
        self.events._path(event_id)
        self.operations._path(operation_id)
        if not isinstance(new_status, ThreadStatus):
            raise ValueError("new_status must be a ThreadStatus")
        with exclusive_write(self.storage.threads_root):
            from core.operations.thread_update import require_no_thread_update
            require_no_thread_update(self.operations.root.parent / 'thread-update-v1', thread_id)
            if self.deletion_operations is not None and any(
                pending.target_id == thread_id
                for pending in self.deletion_operations.list_incomplete()
            ):
                raise OperationConflict("recover Thread deletion before changing status")
            if self.creation_operations is not None:
                for pending in self.creation_operations.list_incomplete():
                    if pending.target_id == thread_id:
                        raise OperationConflict("recover Thread creation before changing status")
            existing = self.operations.get(operation_id)
            if existing is not None:
                if (existing.target_id != thread_id
                        or existing.operation_type is not OperationType.THREAD_STATUS_CHANGE
                        or existing.previous_revision != previous_revision
                        or not isinstance(existing.plan, ThreadStatusChangePlan)
                        or existing.plan.new_status != new_status
                        or existing.plan.event_id != event_id):
                    raise OperationConflict("operation_id reused with a different command")
                return self._resume(existing)
            for pending in self.operations.list_incomplete():
                if pending.target_id == thread_id:
                    raise OperationConflict("recover the pending operation before a new change")
            before = self.storage.get(thread_id)
            if before is None:
                raise OperationConflict("Thread does not exist")
            if before.revision != previous_revision:
                raise ThreadRevisionConflict("Thread revision changed before preparation")
            after = ThreadManager.change_status(before, new_status)
            before_text = self.storage._serialize(before)
            after_text = self.storage._serialize(after)
            # The current Markdown format cannot represent all arbitrary strings.
            # Reject lossy objects instead of preparing an unrecoverable operation.
            if (self.storage._deserialize(before_text) != before
                    or self.storage._deserialize(after_text) != after):
                raise OperationConflict("Thread cannot round-trip through its storage format")
            operation = OperationRecord(
                operation_id, OperationType.THREAD_STATUS_CHANGE, thread_id,
                previous_revision, after.revision, "",
                plan=ThreadStatusChangePlan(new_status, event_id, before_text, after_text),
            )
            operation = replace(operation, execution_plan_hash=plan_hash(operation))
            self.operations.create(operation)
            return self._resume(operation)

    def resume(self, operation_id: str) -> Thread:
        with exclusive_write(self.storage.threads_root):
            operation = self.operations.get(operation_id)
            if operation is None:
                raise OperationNotFound(operation_id)
            return self._resume(operation)

    def _validated_states(self, operation):
        plan = operation.plan
        if (operation.operation_type != OperationType.THREAD_STATUS_CHANGE
                or plan is None or not isinstance(plan.before_state, str)
                or not isinstance(plan.after_state, str)):
            raise OperationConflict("legacy or incomplete plan requires manual migration")
        if plan_hash(operation) != operation.execution_plan_hash:
            raise OperationConflict("execution plan hash mismatch")
        before = self.storage._deserialize(plan.before_state)
        after = self.storage._deserialize(plan.after_state)
        ThreadManager.validate(before)
        ThreadManager.validate(after)
        if (before.thread_id != operation.target_id or after.thread_id != operation.target_id
                or before.revision != operation.previous_revision
                or after.revision != operation.revision):
            raise OperationConflict("snapshot identity or revision mismatch")
        expected = ThreadManager.change_status(before, plan.new_status, timestamp=after.updated_at)
        if expected != after:
            raise OperationConflict("snapshot is not the planned status transition")
        return before, after

    def _event(self, operation, before, after):
        return Event(
            event_id=operation.plan.event_id, revision=after.revision,
            event_type=EventType.STATUS_CHANGED, thread_id=after.thread_id,
            state_transition=StateTransition(
                before={"status": before.status.value}, after={"status": after.status.value}),
            provenance=Provenance(source_type="SYSTEM_GENERATED", source="thread-status-service",
                                  actor="eidolon", timestamp=after.updated_at),
            relations=[EventRelation(RelationType.CAUSED_BY, operation.operation_id)],
        )

    def _resume(self, operation):
        before, after = self._validated_states(operation)
        if operation.status == OperationStatus.COMMITTED:
            # Return the original command result, even if the Thread has since advanced.
            return after
        if operation.status == OperationStatus.FAILED:
            raise OperationConflict("failed operation requires manual resolution")
        from core.operations.thread_update import require_no_thread_update
        require_no_thread_update(self.operations.root.parent / 'thread-update-v1', operation.target_id)
        expected_event = self._event(operation, before, after)
        # Lock event and operation writers as well as Thread writers. The fixed
        # order is Thread -> Operation -> Event; repository calls are reentrant.
        with exclusive_write(self.operations.root), exclusive_write(self.events.events_root):
            current_record = self.operations.get(operation.operation_id)
            if current_record != operation:
                raise OperationConflict("operation changed while acquiring locks")
            current = self.storage.get(operation.target_id)
            if current != before and current != after:
                raise OperationConflict("Thread diverged from both persisted snapshots")
            saved_event = self.events.get(expected_event.event_id)
            if saved_event is not None and saved_event != expected_event:
                raise OperationConflict("event_id already contains a different event")
            if operation.status == OperationStatus.PREPARED:
                operation = replace(operation, status=OperationStatus.APPLYING)
                self.operations.update(operation)
            if current == before:
                self.storage.update(after, operation.previous_revision)
            if saved_event is None:
                self.events.save(expected_event)
            self.operations.update(replace(operation, status=OperationStatus.COMMITTED))
            return after

    def recover(self) -> dict[str, dict[str, str]]:
        """Recover independent records, reporting damaged/conflicting ones individually."""
        results = {}
        for path in sorted(self.operations.root.glob("*.json")):
            try:
                with exclusive_write(self.storage.threads_root):
                    operation = self.operations.get(path.stem)
                    if operation is None or operation.status is OperationStatus.COMMITTED:
                        continue
                    self._resume(operation)
                results[path.stem] = {"status": "COMMITTED"}
            except (OSError, ValueError, TypeError, AttributeError,
                    OperationRepositoryError, EventRepositoryError,
                    ThreadStorageError, ThreadError) as exc:
                results[path.stem] = {"status": "BLOCKED", "error": type(exc).__name__}
        return results
