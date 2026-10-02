"""Human-authorized retry of FAILED Thread creation, deletion, status and update operations, never abandonment.

One atomic journal write records the review and moves FAILED to APPLYING.
Ordinary recovery then finishes the unchanged command with existing guards.
"""
import argparse
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import re

from core.backend.errors import BackendError
from core.backend.filesystem import FilesystemBackend
from core.events.filesystem import FilesystemEventRepository
from core.events.errors import EventRepositoryError
from core.operations.errors import OperationConflict, OperationRepositoryError
from core.operations.filesystem import FilesystemOperationRepository
from core.operations.models import OperationStatus
from core.operations.readiness import check_readiness
from core.operations.thread_create import FilesystemLinkedThreadCreation
from core.operations.thread_delete import FilesystemThreadDeletion
from core.threads.link_service import ThreadInformationLinkService, MissingLinkedInformation
from core.operations.thread_status import FilesystemThreadOperations
from core.operations.thread_update import FilesystemThreadUpdates, read_operations
from core.persistence import exclusive_write, has_symlink_component
from core.storage_format import decode_json_value
from core.threads.manager import ThreadError
from core.threads.storage import ThreadStorage, ThreadStorageError

FAMILY = 'thread-status-v1'
UPDATE_FAMILY = 'thread-update-v1'
CREATE_FAMILY = 'thread-create-v1'
DELETE_FAMILY = 'thread-delete-v1'
ACTIONS = {FAMILY: 'RETRY_THREAD_STATUS_V1', UPDATE_FAMILY: 'RETRY_THREAD_UPDATE_V1',
           CREATE_FAMILY: 'RETRY_THREAD_CREATE_V1',
           DELETE_FAMILY: 'RETRY_THREAD_DELETE_V1'}
READ_ERRORS = (OSError, ValueError, TypeError, OperationRepositoryError,
               EventRepositoryError, ThreadStorageError, ThreadError, BackendError)


def _digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _readers(root, family):
    if family not in ACTIONS:
        raise ValueError('unsupported manual resolution family')
    root = Path(root)
    persistent, history = root / 'memory/persistent', root / 'memory/history'
    for path in (root, persistent, persistent / 'threads', history,
                 history / 'operations' / family, history / 'events' / family):
        if has_symlink_component(path) or (path.exists() and not path.is_dir()):
            raise OperationConflict('unsafe resolution tree')
    storage = ThreadStorage.__new__(ThreadStorage)
    storage.persistent_root, storage.threads_root = persistent, persistent / 'threads'
    if family == DELETE_FAMILY:
        operations = FilesystemOperationRepository.__new__(FilesystemOperationRepository)
        operations.root = history / 'operations' / family
        engine = FilesystemThreadDeletion(storage, operations)
        for attr, name in (('status_operations', FAMILY), ('creation_operations', CREATE_FAMILY)):
            repository = FilesystemOperationRepository.__new__(FilesystemOperationRepository)
            repository.root = history / 'operations' / name
            setattr(engine, attr, repository)
        return engine
    events = FilesystemEventRepository.__new__(FilesystemEventRepository)
    events.events_root = history / 'events' / family
    operations = FilesystemOperationRepository.__new__(FilesystemOperationRepository)
    operations.root = history / 'operations' / family
    if family == FAMILY:
        return FilesystemThreadOperations(storage, events, operations)
    backend = FilesystemBackend.__new__(FilesystemBackend)
    backend.persistent_root, backend.history_root = persistent, history
    backend.pending_delete_root = history / 'pending-delete'
    if family == CREATE_FAMILY:
        engine = FilesystemLinkedThreadCreation.__new__(FilesystemLinkedThreadCreation)
        engine.backend, engine.storage = backend, storage
        engine.events, engine.operations = events, operations
        engine.links = ThreadInformationLinkService(backend, storage)
        engine.deletion_operations = None
        return engine
    engine = FilesystemThreadUpdates.__new__(FilesystemThreadUpdates)
    engine.backend, engine.storage = backend, storage
    engine.events, engine.operations = events, operations
    return engine


def _scope(root, engine, operation, selected_family):
    # Independent FAILED operations of this family may be resolved one at a time.
    # Unknown, corrupt or other pending families block authorization.
    state = check_readiness(root)
    for issue in state['issues']:
        if (operation.status is OperationStatus.APPLYING and issue.get('reason') == 'APPLYING'
                and issue['path'] == 'memory/history/operations/' + selected_family + '/' + operation.operation_id + '.json'):
            continue
        if (issue.get('reason') != 'FAILED'
                or Path(issue['path']).parent.as_posix() != 'memory/history/operations/' + selected_family):
            raise OperationConflict('other unresolved state blocks manual retry')
    if selected_family == UPDATE_FAMILY:
        engine._other_pending(operation.target_id, operation.operation_id)
    for family in ('thread-status-v1', 'thread-create-v1', 'thread-delete-v1', 'thread-update-v1'):
        for other in read_operations(engine.operations.root.parent / family):
            if (family == selected_family and other.operation_id == operation.operation_id):
                continue
            if (selected_family == DELETE_FAMILY and family != selected_family
                    and other.operation_id == operation.operation_id):
                raise OperationConflict('another family reserves this operation identity')
            event_id = getattr(operation.plan, 'event_id', None)
            if (event_id is not None and family == selected_family
                    and getattr(other.plan, 'event_id', None) == event_id):
                raise OperationConflict('another operation reserves this Event identity')
            if (selected_family == CREATE_FAMILY and family == CREATE_FAMILY
                    and other.target_id == operation.target_id):
                raise OperationConflict('another creation reserves this Thread identity')
            if other.target_id == operation.target_id and other.status is not OperationStatus.COMMITTED:
                raise OperationConflict('another operation reserves this Thread')


def review_failed_thread(root, operation_id, *, family=FAMILY):
    """Read-only preview; snapshots remain in the source journal, not this report."""
    engine = _readers(root, family)
    operation = engine.operations.get(operation_id)
    if operation is None or operation.status is not OperationStatus.FAILED:
        raise OperationConflict('a FAILED Thread operation of the selected family is required')
    _scope(root, engine, operation, family)
    before, after = engine._validated_states(operation)
    current = engine.storage.get(operation.target_id)
    if current != before and current != after:
        raise OperationConflict('Thread diverged from both snapshots')
    if family == UPDATE_FAMILY:
        engine._check_links(before, after)
    elif family != DELETE_FAMILY:
        engine.storage._check_concerns(after)
        if family == CREATE_FAMILY and engine.backend.get(operation.plan.information_id) is None:
            raise MissingLinkedInformation(operation.plan.information_id)
    saved = None
    if family != DELETE_FAMILY:
        event = engine._event(operation, before, after)
        saved = engine.events.get(event.event_id)
        if saved is not None and saved != event:
            raise OperationConflict('Event diverged from the planned effect')
        if saved is not None and current != after:
            raise OperationConflict('Event exists without the planned Thread state')
    operation_path = engine.operations._path(operation_id)
    report = {'format_version': 1, 'family': family, 'operation_id': operation_id,
            'target_id': operation.target_id, 'plan_sha256': operation.execution_plan_hash,
            'failed_record_sha256': sha256(operation_path.read_bytes()).hexdigest(),
            'previous_revision': operation.previous_revision, 'revision': operation.revision,
            'thread_state': ('ABSENT' if family == CREATE_FAMILY else 'BEFORE') if current == before
                else ('ABSENT' if family == DELETE_FAMILY else 'AFTER'),
            'event_state': 'NOT_APPLICABLE' if family == DELETE_FAMILY else ('ABSENT' if saved is None else 'MATCH'),
            'write_thread': family != DELETE_FAMILY and current == before,
            'write_event': family != DELETE_FAMILY and saved is None,
            'previous_resolutions': deepcopy(operation.manual_resolutions),
            'action': ACTIONS[family]}
    if family == DELETE_FAMILY:
        report['delete_thread'] = current is not None
    if family == CREATE_FAMILY:
        report['information_id'] = operation.plan.information_id
    if family == UPDATE_FAMILY:
        report['command'] = decode_json_value(operation.plan.command)
    return report


def _checkpoint(stage):
    """Durable retry boundaries for interruption tests."""


def retry_failed_thread(root, review, *, resolution_id, actor, reason, timestamp):
    """Validate an explicit review again under locks, append authorization, retry.

    A stale preview cannot approve a changed FAILED record. A published retry is
    resumed by this call or ordinary recover-all; replay never grants a second
    authorization or recreates a deleted terminal Thread.
    """
    if (not isinstance(review, dict) or type(review.get('format_version')) is not int
            or review.get('format_version') != 1
            or not isinstance(review.get('family'), str) or review['family'] not in ACTIONS):
        raise ValueError('a supported Thread resolution review is required')
    family = review['family']
    if not isinstance(resolution_id, str) or not re.fullmatch('[A-Za-z0-9._-]+', resolution_id):
        raise ValueError('resolution_id required')
    entry = {'resolution_id': resolution_id, 'action': ACTIONS[family],
             'actor': actor, 'reason': reason, 'timestamp': timestamp,
             'failed_record_sha256': review.get('failed_record_sha256'), 'review_sha256': _digest(review)}
    engine = _readers(root, family)
    operation_id = review.get('operation_id')
    operation = engine.operations.get(operation_id)
    if operation is None:
        raise OperationConflict('operation is missing')
    # Validate audit metadata before acquiring/creating any lock or directory.
    candidate = replace(operation, status=OperationStatus.APPLYING,
                        manual_resolutions=[*operation.manual_resolutions, entry])
    existing = next((item for item in operation.manual_resolutions
                     if item['resolution_id'] == resolution_id), None)
    if existing is None:
        engine.operations._validate_record_fields(candidate)
    elif existing != entry:
        raise OperationConflict('resolution_id reused with a different review or decision')
    with ExitStack() as locks:
        locks.enter_context(exclusive_write(engine.storage.persistent_root))
        locks.enter_context(exclusive_write(engine.storage.threads_root))
        locks.enter_context(exclusive_write(engine.operations.root))
        # FAILED journals produced by the coordinator already have this directory;
        # a restored valid journal may need it initialized after review.
        if family != DELETE_FAMILY:
            engine.events.events_root.mkdir(parents=True, exist_ok=True)
            locks.enter_context(exclusive_write(engine.events.events_root))
        operation = engine.operations.get(operation_id)
        if operation is None:
            raise OperationConflict('operation disappeared before authorization')
        existing = next((item for item in operation.manual_resolutions
                         if item['resolution_id'] == resolution_id), None)
        if existing is not None:
            if existing != entry:
                raise OperationConflict('resolution_id reused with a different decision')
            if operation.status is OperationStatus.FAILED:
                raise OperationConflict('retry failed again; a new review and resolution_id are required')
            if operation.status not in {OperationStatus.APPLYING, OperationStatus.COMMITTED}:
                raise OperationConflict('invalid authorized retry state')
            if operation.status is OperationStatus.APPLYING:
                _scope(root, engine, operation, family)
        else:
            if _digest(review_failed_thread(root, operation_id, family=family)) != _digest(review):
                raise OperationConflict('review changed before authorization')
            operation = replace(operation, status=OperationStatus.APPLYING,
                                manual_resolutions=[*operation.manual_resolutions, entry])
            _checkpoint('before_authorization')
            # Specialized transition only: generic update() still forbids FAILED
            # exits and changes to the append-only authorization history.
            engine.operations._write(operation, engine.operations._path(operation_id))
            _checkpoint('after_authorization')
        result = engine._resume(operation)
        _checkpoint('after_commit')
        return {'status': 'COMMITTED', 'resolution_id': resolution_id, 'operation_id': operation_id,
                'thread_id': operation.target_id if family == DELETE_FAMILY else result.thread_id,
                'revision': operation.revision if family == DELETE_FAMILY else result.revision}


def review_failed_status(root, operation_id):
    """Compatibility API for status-only previews."""
    return review_failed_thread(root, operation_id, family=FAMILY)


def retry_failed_status(root, review, **decision):
    """Compatibility API: never authorize an update through the status API."""
    if not isinstance(review, dict) or review.get('family') != FAMILY:
        raise ValueError('a Thread status resolution review is required')
    return retry_failed_thread(root, review, **decision)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    preview = commands.add_parser('preview')
    preview.add_argument('operation_id')
    preview.add_argument('--family', choices=tuple(ACTIONS), default=FAMILY)
    retry = commands.add_parser('retry')
    retry.add_argument('--review', type=Path, required=True)
    for name in ('resolution-id', 'actor', 'reason', 'timestamp'):
        retry.add_argument('--' + name, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'preview':
            report = review_failed_thread(args.root, args.operation_id, family=args.family)
        else:
            report = retry_failed_thread(args.root, decode_json_value(args.review.read_text(encoding='utf-8')),
                                         resolution_id=args.resolution_id, actor=args.actor,
                                         reason=args.reason, timestamp=args.timestamp)
    except READ_ERRORS as exc:
        print(json.dumps({'status': 'BLOCKED', 'reason': str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
