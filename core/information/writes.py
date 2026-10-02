"""Explicit, journaled Information writes; files remain canonical.

Business calls require stable command IDs, actor and timestamp. Imports keep
using MemoryBackend. No recovery or compaction runs implicitly on startup.
"""
from dataclasses import asdict, replace
import hashlib
import json

from core.backend.errors import BackendError
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.events.errors import EventRepositoryError
from core.events.filesystem import FilesystemEventRepository
from core.events.models import Event, EventType, EventRelation, RelationType, Provenance, StateTransition
from core.events.validator import validate_event
from core.operations.errors import OperationConflict, OperationNotFound, OperationRepositoryError
from core.operations.filesystem import FilesystemOperationRepository
from core.operations.models import (
    InformationCreatePlan, InformationUpdatePlan, OperationRecord, OperationType, OperationStatus,
)
from core.operations.thread_status import plan_hash
from core.persistence import exclusive_write
from core.information.write_journal import InformationWriteJournal, JOURNAL


CLASSIFICATION = ('type', 'epistemic_status', 'operational_state', 'confidence', 'importance', 'retention')


def canonical_json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def fingerprint(kind, after, previous_revision, event_id, actor, timestamp):
    """v1: exact JSON values; list order and Unicode codepoints are significant."""
    command = dict(format_version=1, operation_type=kind.value,
                   previous_revision=previous_revision, memory=asdict(after),
                   event_id=event_id, actor=actor, timestamp=timestamp)
    return hashlib.sha256(canonical_json(command).encode('utf-8')).hexdigest()


def operation_result(operation):
    return dict(information_id=operation.target_id, previous_revision=operation.previous_revision,
                revision=operation.revision, event_id=operation.plan.event_id)


def expected_event(operation, backend):
    plan = operation.plan
    after = backend._deserialize(plan.after_state)
    before = backend._deserialize(plan.before_state) if isinstance(plan, InformationUpdatePlan) else None
    def state(memory):
        if memory is None:
            return {}
        result = {key: memory.metadata[key] for key in CLASSIFICATION if key in memory.metadata}
        # None means unlabelled, never an inferred CONFIRMED state.
        if not {'epistemic_status', 'operational_state'} & result.keys():
            result['epistemic_status'] = None
        result['content_sha256'] = hashlib.sha256(canonical_json(memory.content).encode('utf-8')).hexdigest()
        return result
    old, new = state(before), state(after)
    if before is not None:
        changed = {key for key in old.keys() | new.keys() if old.get(key) != new.get(key)}
        # Existing Event contract requires an Information state on each side.
        changed |= {'epistemic_status', 'operational_state'} & (old.keys() | new.keys())
        old = {key: old.get(key) for key in changed}
        new = {key: new.get(key) for key in changed}
    return Event(plan.event_id, operation.revision,
                 EventType.CREATED if before is None else EventType.UPDATED,
                 information_id=operation.target_id, state_transition=StateTransition(old, new),
                 provenance=Provenance('SYSTEM_GENERATED', 'information-service', plan.actor, plan.timestamp),
                 relations=[EventRelation(RelationType.CAUSED_BY, operation.operation_id)])


def validate_operation(op, backend):
    if (not isinstance(op.plan, InformationCreatePlan)
            or op.operation_type not in {OperationType.INFORMATION_CREATE, OperationType.INFORMATION_UPDATE}
            or plan_hash(op) != op.execution_plan_hash):
        raise OperationConflict('invalid Information write plan')
    plan = op.plan
    after = backend._deserialize(plan.after_state)
    before = backend._deserialize(plan.before_state) if isinstance(plan, InformationUpdatePlan) else None
    if (after.information_id != op.target_id or after.revision != op.revision
            or (before is not None and (before.information_id != op.target_id
                                       or before.revision != op.previous_revision))
            or fingerprint(op.operation_type, after, op.previous_revision, plan.event_id,
                           plan.actor, plan.timestamp) != plan.command_fingerprint):
        raise OperationConflict('Information snapshots differ from command')
    return before, after


class FilesystemInformationWrites:
    def __init__(self, backend: FilesystemBackend):
        # Canonical locations ensure deletion sees every business operation.
        self.backend = backend
        self.operations = FilesystemOperationRepository(backend.history_root / 'operations' / JOURNAL)
        self.events = FilesystemEventRepository(backend.history_root / 'events' / JOURNAL)
        self.journal = InformationWriteJournal(backend.history_root)

    def create(self, memory: Memory, *, operation_id: str, event_id: str,
               actor: str, timestamp: str) -> dict:
        if memory.revision != 1:
            raise OperationConflict('new Information must start at revision 1')
        return self._execute(OperationType.INFORMATION_CREATE, memory, 0,
                             operation_id, event_id, actor, timestamp)

    def update(self, memory: Memory, *, previous_revision: int, operation_id: str,
               event_id: str, actor: str, timestamp: str) -> dict:
        if memory.revision != previous_revision or previous_revision < 1:
            raise OperationConflict('Memory revision must match previous_revision')
        return self._execute(OperationType.INFORMATION_UPDATE, memory, previous_revision,
                             operation_id, event_id, actor, timestamp)

    def execute_batch(self, commands):
        """Execute 1–100 explicit JSON commands; retain inputs for stable replay."""
        from core.information.batch import execute_batch
        return execute_batch(self, commands)

    def _deletion_status(self, target_id):
        path = self.backend.pending_delete_root / f'{target_id}.json'
        if path.exists() or path.is_symlink():
            return self.backend._load_delete_request(path, target_id)['status']
        return None

    def _check_deletion(self, kind, target_id):
        status = self._deletion_status(target_id)
        if status is not None and not (
            kind is OperationType.INFORMATION_UPDATE and status == 'CANCELLED'
        ):
            raise OperationConflict(f'Information reserved by {status}')

    def _pending(self, target_id, *, excluding=None):
        self.journal.reservations().require_available(target_id, excluding)

    def _execute(self, kind, memory, previous, opid, event_id, actor, timestamp, *, reservations=None):
        self.backend._validate_memory_shape(memory)
        self.backend._path(memory.information_id)
        self.operations._path(opid)
        self.events._path(event_id)
        after = replace(memory, revision=previous + 1)
        snapshot = self.backend._serialize_checked(after)
        digest = fingerprint(kind, after, previous, event_id, actor, timestamp)
        with exclusive_write(self.backend.persistent_root), exclusive_write(self.operations.root), exclusive_write(self.events.events_root):
            entry = self.journal.read(opid)
            if entry is not None:
                if entry.fingerprint != digest:
                    raise OperationConflict('operation_id reused with a different command')
                return entry.result if entry.receipt is not None else self._resume(entry.operation, reservations)
            from core.routing.execution_journal import require_available
            require_available(self.backend.history_root, information_id=after.information_id)
            self._check_deletion(kind, after.information_id)
            if reservations is None:
                reservations = self.journal.reservations()
            reservations.require_available(after.information_id)
            current = self.backend.get(after.information_id)
            if kind is OperationType.INFORMATION_CREATE:
                if current is not None:
                    raise OperationConflict('Information already exists')
                plan = InformationCreatePlan(event_id, snapshot, actor, timestamp, digest)
            else:
                if current is None or current.revision != previous:
                    raise OperationConflict('Information revision differs from previous_revision')
                plan = InformationUpdatePlan(event_id, snapshot, actor, timestamp, digest,
                                             self.backend._serialize_checked(current))
            self.backend._ensure_relations_do_not_reuse_deleted_identity(after)
            op = OperationRecord(opid, kind, after.information_id, previous, previous + 1, '', plan=plan)
            op = replace(op, execution_plan_hash=plan_hash(op))
            event = expected_event(op, self.backend)
            errors = validate_event(event)
            if errors:
                raise OperationConflict('; '.join(errors))
            if self.events.get(event_id) is not None:
                raise OperationConflict('event_id already contains an event')
            # Reserve an Event even before it is persisted by another pending command.
            if event_id in reservations.event_ids:
                raise OperationConflict('event_id reserved by another operation')
            self.operations.create(op)
            # The same Persistent/Operation/Event locks remain held. Only our
            # new operation was added; _resume excludes that operation anyway.
            return self._resume(op, reservations)

    def _resume(self, op, reservations=None):
        before, after = validate_operation(op, self.backend)
        if op.status is OperationStatus.COMMITTED:
            return operation_result(op)
        if op.status is OperationStatus.FAILED:
            raise OperationConflict('failed operation requires manual resolution')
        from core.routing.execution_journal import require_available
        require_available(self.backend.history_root, information_id=op.target_id)
        self._check_deletion(op.operation_type, op.target_id)
        if reservations is None:
            reservations = self.journal.reservations()
        reservations.require_available(op.target_id, excluding=op.operation_id)
        current = self.backend.get(op.target_id)
        if current != before and current != after:
            raise OperationConflict('Information diverged from write snapshots')
        self.backend._ensure_relations_do_not_reuse_deleted_identity(after)
        event = expected_event(op, self.backend)
        saved = self.events.get(op.plan.event_id)
        if saved is not None and saved != event:
            raise OperationConflict('event_id already contains a different event')
        if op.status is OperationStatus.PREPARED:
            op = replace(op, status=OperationStatus.APPLYING)
            self.operations.update(op)
        if current != after:
            self.backend._atomic_write(self.backend._path(op.target_id), op.plan.after_state)
        if saved is None:
            self.events.save(event)
        self.operations.update(replace(op, status=OperationStatus.COMMITTED))
        return operation_result(op)

    def resume(self, operation_id):
        with exclusive_write(self.backend.persistent_root), exclusive_write(self.operations.root), exclusive_write(self.events.events_root):
            entry = self.journal.read(operation_id)
            if entry is None:
                raise OperationNotFound(operation_id)
            if entry.receipt is not None:
                if entry.operation is not None:
                    from core.information.compaction import compact_locked
                    return compact_locked(self, operation_id)
                return entry.result
            return self._resume(entry.operation)

    def recover(self):
        results = {}
        for opid in self.journal.ids():
            try:
                self.resume(opid)
                results[opid] = {'status': 'COMMITTED'}
            except (OSError, ValueError, TypeError, BackendError, OperationRepositoryError, EventRepositoryError) as exc:
                results[opid] = {'status': 'BLOCKED', 'error': type(exc).__name__}
        return results

    def compact(self, operation_id):
        from core.information.compaction import compact_locked
        with exclusive_write(self.backend.persistent_root), exclusive_write(self.operations.root), exclusive_write(self.events.events_root):
            return compact_locked(self, operation_id)
