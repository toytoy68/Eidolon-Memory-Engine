"""Recoverable project commands. Canonical lock order: Persistent → Thread → Operation → Event."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

from core.backend.errors import InvalidMemory, InformationDeletionBlocked
from core.events.errors import EventRepositoryError
from core.events.filesystem import FilesystemEventRepository
from core.events.models import Event, EventType, EventRelation, RelationType, Provenance, StateTransition
from core.information.references import ensure_information_write_safety
from core.operations.errors import OperationConflict, OperationNotFound, OperationRepositoryError
from core.operations.filesystem import FilesystemOperationRepository
from core.operations.models import OperationRecord, OperationType, OperationStatus, ThreadUpdatePlan
from core.operations.thread_status import plan_hash
from core.persistence import exclusive_write, has_symlink_component
from core.storage_format import decode_json_value
from core.threads.manager import ThreadManager, ThreadError
from core.threads.models import ThreadAction, ActionStatus, ThreadStatus
from core.threads.storage import ThreadStorage, ThreadStorageError, ThreadRevisionConflict


OTHER_FAMILIES = ('thread-create-v1', 'thread-status-v1', 'thread-delete-v1')


def read_operations(root):
    """Read an optional journal without creating directories or following links."""
    root = Path(root)
    if has_symlink_component(root) or (root.exists() and not root.is_dir()):
        raise OperationConflict('unsafe Thread journal')
    repository = FilesystemOperationRepository.__new__(FilesystemOperationRepository)
    repository.root = root
    for path in sorted(root.glob('*.json')):
        record = repository.get(path.stem)
        if record is not None:
            yield record


def require_no_thread_update(journal_root, thread_id):
    from core.routing.execution_journal import require_available
    require_available(Path(journal_root).parent.parent, thread_id=thread_id)
    for record in read_operations(journal_root):
        if record.target_id == thread_id and record.status is not OperationStatus.COMMITTED:
            raise OperationConflict('recover Thread update before another mutation')


def command_text(command):
    if not isinstance(command, dict):
        raise ValueError('Thread command must be an object')
    shapes = {'LINK': {'information_id'}, 'UNLINK': {'information_id'},
              'ADD_ACTION': {'action'}, 'ACTION_STATUS': {'action_id', 'status'},
              'DETAILS': {'fields'}}
    kind = command.get('kind')
    if not isinstance(kind, str) or kind not in shapes or set(command) != shapes[kind] | {'kind'}:
        raise ValueError('unknown Thread command or fields')
    if kind in {'LINK', 'UNLINK'}:
        ThreadStorage._validate_id(command['information_id'])
    elif kind == 'ADD_ACTION':
        action = command['action']
        if not isinstance(action, dict) or set(action) != {'action_id', 'description', 'status', 'metadata'}:
            raise ValueError('complete Thread action required')
        ActionStatus(action['status'])
    elif kind == 'ACTION_STATUS':
        if not isinstance(command['action_id'], str) or not command['action_id']:
            raise ValueError('action_id required')
        ActionStatus(command['status'])
    elif kind == 'DETAILS':
        fields = command['fields']
        if not isinstance(fields, dict) or not fields or set(fields) - {'title', 'objective', 'context'}:
            raise ValueError('DETAILS accepts title, objective and context only')
    text = json.dumps(command, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    if decode_json_value(text) != command:
        raise ValueError('lossy Thread command')
    return text


def apply_command(before, command, timestamp):
    """Pure domain transition, also used to validate persisted recovery snapshots."""
    command_text(command)
    ThreadManager.validate(before)
    if before.status in {ThreadStatus.COMPLETED, ThreadStatus.CANCELLED}:
        raise OperationConflict('cannot modify a closed Thread')
    kind = command['kind']
    if kind in {'LINK', 'UNLINK'}:
        identity = command['information_id']
        targets = ThreadStorage._concerns(before)
        if (kind == 'LINK') == (identity in targets):
            raise OperationConflict('link already present or absent')
        relations = deepcopy(before.relations)
        if kind == 'LINK':
            relations.append({'type': 'CONCERNS', 'target_id': identity})
        else:
            relations = [r for r in relations if not (
                r.get('type') == 'CONCERNS' and (r.get('target_id') if r.get('target_id') is not None else r.get('target')) == identity)]
        after = replace(before, relations=relations, revision=before.revision + 1)
    elif kind == 'ADD_ACTION':
        fields = deepcopy(command['action'])
        fields['status'] = ActionStatus(fields['status'])
        after = ThreadManager.add_action(before, ThreadAction(**fields))
    elif kind == 'ACTION_STATUS':
        after = ThreadManager.update_action_status(before, command['action_id'], ActionStatus(command['status']))
    else:
        after = replace(before, **deepcopy(command['fields']), revision=before.revision + 1)
    after = replace(after, updated_at=timestamp)
    ThreadManager.validate(after)
    return after


class FilesystemThreadUpdates:
    def __init__(self, backend):
        self.backend = backend
        self.storage = ThreadStorage(backend.persistent_root)
        self.operations = FilesystemOperationRepository(backend.history_root / 'operations/thread-update-v1')
        self.events = FilesystemEventRepository(backend.history_root / 'events/thread-update-v1')

    def _other_pending(self, thread_id, operation_id):
        from core.routing.execution_journal import require_available
        require_available(self.backend.history_root, thread_id=thread_id)
        for family in OTHER_FAMILIES:
            for record in read_operations(self.operations.root.parent / family):
                if record.operation_id == operation_id or (
                    record.target_id == thread_id and record.status is not OperationStatus.COMMITTED
                ):
                    raise OperationConflict('recover other Thread operation before update')
        for record in read_operations(self.operations.root):
            if (record.operation_id != operation_id and record.target_id == thread_id
                    and record.status is not OperationStatus.COMMITTED):
                raise OperationConflict('recover pending Thread update first')

    def _check_links(self, before, after, *, preparing=False):
        # Additions reserve their targets through the journal even before the
        # Thread file changes. A deletion request arriving afterwards may wait;
        # approving it remains blocked until this command and its link resolve.
        self.storage._check_concerns(after)
        for identity in self.storage._concerns(after) - self.storage._concerns(before):
            ensure_information_write_safety(self.backend.history_root, identity)
            if preparing:
                path = self.backend.pending_delete_root / (identity + '.json')
                if path.is_symlink():
                    raise OperationConflict('unsafe Information deletion receipt')
                if path.exists():
                    request = self.backend._load_delete_request(path, identity)
                    if request['status'] != 'CANCELLED':
                        raise OperationConflict('resolve Information deletion before linking')

    def execute(self, thread_id, command, *, previous_revision, operation_id,
                event_id, actor, timestamp):
        command = command_text(command)
        self.storage._path(thread_id)
        self.operations._path(operation_id)
        self.events._path(event_id)
        if type(previous_revision) is not int or previous_revision < 1:
            raise ValueError('previous_revision must be a positive integer')
        if not isinstance(actor, str) or not actor or not isinstance(timestamp, str) or not timestamp:
            raise ValueError('explicit actor and timestamp required')
        with exclusive_write(self.backend.persistent_root), exclusive_write(self.storage.threads_root):
            existing = self.operations.get(operation_id)
            if existing is not None:
                plan = existing.plan
                if (existing.operation_type is not OperationType.THREAD_UPDATE
                        or existing.target_id != thread_id or existing.previous_revision != previous_revision
                        or (plan.command, plan.event_id, plan.actor, plan.timestamp) !=
                           (command, event_id, actor, timestamp)):
                    raise OperationConflict('operation_id reused with a different Thread command')
                return self._resume(existing)
            self._other_pending(thread_id, operation_id)
            before = self.storage.get(thread_id)
            if before is None:
                raise OperationConflict('Thread does not exist')
            if before.revision != previous_revision:
                raise ThreadRevisionConflict('Thread revision changed before update')
            after = apply_command(before, decode_json_value(command), timestamp)
            self._check_links(before, after, preparing=True)
            if self.events.get(event_id) is not None or any(
                record.plan.event_id == event_id for record in read_operations(self.operations.root)
            ):
                raise OperationConflict('event_id already reserved')
            plan = ThreadUpdatePlan(command, event_id, actor, timestamp,
                                    self.storage._serialize_checked(before), self.storage._serialize_checked(after))
            operation = OperationRecord(operation_id, OperationType.THREAD_UPDATE, thread_id,
                                        previous_revision, after.revision, '', plan=plan)
            operation = replace(operation, execution_plan_hash=plan_hash(operation))
            self.operations.create(operation)
            return self._resume(operation)

    def _validated_states(self, operation):
        if (operation.operation_type is not OperationType.THREAD_UPDATE
                or type(operation.plan) is not ThreadUpdatePlan
                or plan_hash(operation) != operation.execution_plan_hash):
            raise OperationConflict('invalid Thread update plan')
        plan = operation.plan
        before, after = (self.storage._deserialize(text) for text in (plan.before_state, plan.after_state))
        if (before.thread_id != operation.target_id or after.thread_id != operation.target_id
                or before.revision != operation.previous_revision or after.revision != operation.revision
                or apply_command(before, decode_json_value(plan.command), plan.timestamp) != after):
            raise OperationConflict('Thread snapshots do not match command')
        return before, after

    @staticmethod
    def _event(operation, before, after):
        plan = operation.plan
        return Event(plan.event_id, after.revision, EventType.UPDATED, thread_id=after.thread_id,
                      state_transition=StateTransition(
                          before={'revision': before.revision, 'snapshot_sha256': sha256(plan.before_state.encode()).hexdigest()},
                          after={'revision': after.revision, 'snapshot_sha256': sha256(plan.after_state.encode()).hexdigest(),
                                 'command': decode_json_value(plan.command)['kind']}),
                      provenance=Provenance('SYSTEM_GENERATED', 'thread-update-service', plan.actor, plan.timestamp),
                      relations=[EventRelation(RelationType.CAUSED_BY, operation.operation_id)])

    def _resume(self, operation):
        before, after = self._validated_states(operation)
        if operation.status is OperationStatus.COMMITTED:
            return after
        if operation.status is OperationStatus.FAILED:
            raise OperationConflict('failed Thread update requires manual resolution')
        self._other_pending(operation.target_id, operation.operation_id)
        self._check_links(before, after)
        plan = operation.plan
        event = self._event(operation, before, after)
        with exclusive_write(self.operations.root), exclusive_write(self.events.events_root):
            if self.operations.get(operation.operation_id) != operation:
                raise OperationConflict('operation changed while acquiring locks')
            current = self.storage.get(operation.target_id)
            if current != before and current != after:
                raise OperationConflict('Thread diverged from update snapshots')
            saved = self.events.get(plan.event_id)
            if saved is not None and saved != event:
                raise OperationConflict('event_id already contains a different event')
            if operation.status is OperationStatus.PREPARED:
                operation = replace(operation, status=OperationStatus.APPLYING)
                self.operations.update(operation)
            if current == before:
                self.storage._update_coordinated(before, after)
            if saved is None:
                self.events.save(event)
            self.operations.update(replace(operation, status=OperationStatus.COMMITTED))
        return after

    def resume(self, operation_id):
        with exclusive_write(self.backend.persistent_root), exclusive_write(self.storage.threads_root):
            operation = self.operations.get(operation_id)
            if operation is None:
                raise OperationNotFound(operation_id)
            return self._resume(operation)

    def recover(self):
        result = {}
        for path in sorted(self.operations.root.glob('*.json')):
            try:
                with exclusive_write(self.backend.persistent_root), exclusive_write(self.storage.threads_root):
                    operation = self.operations.get(path.stem)
                    if operation is None or operation.status is OperationStatus.COMMITTED:
                        continue
                    self._resume(operation)
                result[path.stem] = {'status': 'COMMITTED'}
            except (OSError, ValueError, TypeError, OperationRepositoryError, EventRepositoryError,
                    InvalidMemory, ThreadStorageError, ThreadError, InformationDeletionBlocked) as exc:
                result[path.stem] = {'status': 'BLOCKED', 'error': type(exc).__name__}
        return result
