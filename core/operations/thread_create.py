"""Recoverable creation of a Thread linked to an existing Information."""

from __future__ import annotations

from dataclasses import replace

from core.backend.filesystem import FilesystemBackend
from core.events.filesystem import FilesystemEventRepository
from core.events.models import Event, EventRelation, EventType, Provenance, RelationType, StateTransition
from core.operations.errors import OperationConflict, OperationNotFound, OperationRepositoryError
from core.operations.filesystem import FilesystemOperationRepository
from core.operations.models import (
    OperationRecord, OperationStatus, OperationType, ThreadCreatePlan,
)
from core.operations.thread_status import plan_hash
from core.persistence import exclusive_write
from core.threads.link_service import MissingLinkedInformation, ThreadInformationLinkService
from core.threads.manager import ThreadManager, ThreadError
from core.threads.models import Thread
from core.threads.storage import ThreadStorage, ThreadStorageError
from core.events.errors import EventRepositoryError


class FilesystemLinkedThreadCreation:
    """Journal the linked Thread and its CREATED Event before either write."""

    def __init__(self, backend: FilesystemBackend, storage: ThreadStorage,
                 events: FilesystemEventRepository,
                 operations: FilesystemOperationRepository) -> None:
        self.links = ThreadInformationLinkService(backend, storage)
        self.backend = backend
        self.storage = storage
        self.events = events
        self.operations = operations

    def create(self, thread: Thread, information_id: str, *,
               operation_id: str, event_id: str) -> Thread:
        linked = self.links.prepare(thread, information_id)
        self.storage._path(linked.thread_id)
        self.backend._path(information_id)
        self.operations._path(operation_id)
        self.events._path(event_id)
        snapshot = self.storage._serialize(linked)
        if self.storage._deserialize(snapshot) != linked:
            raise OperationConflict("Thread cannot round-trip through its storage format")
        # The backend deletion guard takes persistent -> threads in this order.
        with exclusive_write(self.backend.persistent_root), exclusive_write(self.storage.threads_root):
            existing = self.operations.get(operation_id)
            if existing is not None:
                expected = existing.plan
                if (existing.operation_type is not OperationType.THREAD_CREATE
                        or existing.target_id != linked.thread_id
                        or not isinstance(expected, ThreadCreatePlan)
                        or expected.information_id != information_id
                        or expected.event_id != event_id
                        or expected.after_state != snapshot):
                    raise OperationConflict("operation_id reused with a different command")
                return self._resume(existing)
            if self.backend.get(information_id) is None:
                raise MissingLinkedInformation(information_id)
            if self.storage.get(linked.thread_id) is not None:
                raise OperationConflict("Thread already exists")
            operation = OperationRecord(
                operation_id, OperationType.THREAD_CREATE, linked.thread_id,
                0, 1, "", plan=ThreadCreatePlan(information_id, event_id, snapshot),
            )
            operation = replace(operation, execution_plan_hash=plan_hash(operation))
            self.operations.create(operation)
            return self._resume(operation)

    def _resume(self, operation: OperationRecord) -> Thread:
        if (operation.operation_type is not OperationType.THREAD_CREATE
                or not isinstance(operation.plan, ThreadCreatePlan)
                or plan_hash(operation) != operation.execution_plan_hash):
            raise OperationConflict("invalid Thread creation plan")
        plan = operation.plan
        linked = self.storage._deserialize(plan.after_state)
        ThreadManager.validate(linked)
        if (linked.thread_id != operation.target_id or linked.revision != 1
                or operation.previous_revision != 0 or operation.revision != 1
                or self.links.prepare(linked, plan.information_id) != linked):
            raise OperationConflict("invalid linked Thread snapshot")
        if operation.status is OperationStatus.COMMITTED:
            return linked
        if operation.status is OperationStatus.FAILED:
            raise OperationConflict("failed operation requires manual resolution")
        if self.backend.get(plan.information_id) is None:
            raise MissingLinkedInformation(plan.information_id)
        event = Event(
            event_id=plan.event_id, revision=1, event_type=EventType.CREATED,
            thread_id=linked.thread_id,
            state_transition=StateTransition(after={"status": linked.status.value}),
            provenance=Provenance(source_type="SYSTEM_GENERATED", source="thread-create-service",
                                  actor="eidolon", timestamp=linked.created_at),
            relations=[EventRelation(RelationType.CONCERNS, plan.information_id),
                       EventRelation(RelationType.CAUSED_BY, operation.operation_id)],
        )
        # Lock order: persistent -> Thread -> Operation -> Event.
        with exclusive_write(self.operations.root), exclusive_write(self.events.events_root):
            if self.operations.get(operation.operation_id) != operation:
                raise OperationConflict("operation changed while acquiring locks")
            current = self.storage.get(linked.thread_id)
            if current is not None and current != linked:
                raise OperationConflict("Thread diverged from creation snapshot")
            saved_event = self.events.get(plan.event_id)
            if saved_event is not None and saved_event != event:
                raise OperationConflict("event_id already contains a different event")
            if operation.status is OperationStatus.PREPARED:
                operation = replace(operation, status=OperationStatus.APPLYING)
                self.operations.update(operation)
            if current is None:
                self.storage.create(linked)
            if saved_event is None:
                self.events.save(event)
            self.operations.update(replace(operation, status=OperationStatus.COMMITTED))
        return linked

    def resume(self, operation_id: str) -> Thread:
        with exclusive_write(self.backend.persistent_root), exclusive_write(self.storage.threads_root):
            operation = self.operations.get(operation_id)
            if operation is None:
                raise OperationNotFound(operation_id)
            return self._resume(operation)

    def recover(self) -> dict[str, dict[str, str]]:
        results = {}
        for path in sorted(self.operations.root.glob("*.json")):
            try:
                with exclusive_write(self.backend.persistent_root), exclusive_write(self.storage.threads_root):
                    operation = self.operations.get(path.stem)
                    if operation is None or operation.status in {
                        OperationStatus.COMMITTED, OperationStatus.FAILED,
                    }:
                        continue
                    self._resume(operation)
                results[path.stem] = {"status": "COMMITTED"}
            except (OSError, ValueError, TypeError, AttributeError, OperationRepositoryError,
                    EventRepositoryError, ThreadStorageError, ThreadError) as exc:
                results[path.stem] = {"status": "BLOCKED", "error": str(exc)}
        return results
