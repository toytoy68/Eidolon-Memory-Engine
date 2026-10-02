"""Human-authorized retry of FAILED Information writes, with durable audit history.

The original command is resumed after an atomic audit/APPLYING publication.
Compaction preserves the audit in the content-free terminal receipt.
"""
import argparse
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

from core.backend.filesystem import FilesystemBackend
from core.events.filesystem import FilesystemEventRepository
from core.information.write_journal import InformationWriteJournal, JOURNAL
from core.information.writes import FilesystemInformationWrites, validate_operation, expected_event
from core.operations.errors import OperationConflict
from core.operations.failed_resolution import _digest, READ_ERRORS
from core.operations.filesystem import FilesystemOperationRepository
from core.operations.models import OperationStatus, OperationType
from core.operations.readiness import check_readiness
from core.persistence import exclusive_write, has_symlink_component
from core.storage_format import decode_json_value

ACTION = 'RETRY_INFORMATION_WRITE_V1'


def _reader(root):
    root = Path(root)
    persistent, history = root / 'memory/persistent', root / 'memory/history'
    for path in (root, persistent, history, history / 'events' / JOURNAL):
        if has_symlink_component(path) or (path.exists() and not path.is_dir()):
            raise OperationConflict('unsafe Information resolution tree')
    backend = FilesystemBackend.__new__(FilesystemBackend)
    backend.persistent_root, backend.history_root = persistent, history
    backend.pending_delete_root = history / 'pending-delete'
    writer = FilesystemInformationWrites.__new__(FilesystemInformationWrites)
    writer.backend = backend
    writer.journal = InformationWriteJournal(history)
    writer.journal._check_roots()
    writer.operations = writer.journal.operations
    writer.events = FilesystemEventRepository.__new__(FilesystemEventRepository)
    writer.events.events_root = history / 'events' / JOURNAL
    return writer


def _scope(root, writer, operation):
    # Independent FAILED Information writes may be reviewed one at a time.
    # Any other family, corrupt/unknown source or independent active work blocks.
    for issue in check_readiness(root)['issues']:
        if (issue.get('path') == 'memory/history/information-write-v1'
                and issue.get('reason') == 'requires_recovery_or_review'):
            entry = writer.journal.read(issue.get('operation_id'))
            if entry is not None and entry.operation is not None:
                other = entry.operation
                if other.status is OperationStatus.FAILED or (
                        operation.status is OperationStatus.APPLYING
                        and other.operation_id == operation.operation_id
                        and other.status is OperationStatus.APPLYING):
                    continue
        raise OperationConflict('other unresolved state blocks Information manual retry')
    writer.journal.reservations().require_available(operation.target_id, operation.operation_id)
    for opid in writer.journal.ids():
        if opid == operation.operation_id:
            continue
        entry = writer.journal.read(opid)
        if entry is not None and entry.result['event_id'] == operation.plan.event_id:
            raise OperationConflict('another Information operation reserves this Event identity')
    from core.routing.execution_journal import require_available
    require_available(writer.backend.history_root, information_id=operation.target_id)
    writer._check_deletion(operation.operation_type, operation.target_id)


def review_failed_information(root, operation_id):
    """Read-only review of the original snapshots, including partially saved effects."""
    writer = _reader(root)
    entry = writer.journal.read(operation_id)
    if entry is None or entry.receipt is not None or entry.operation.status is not OperationStatus.FAILED:
        raise OperationConflict('a FAILED Information write is required')
    operation = entry.operation
    _scope(root, writer, operation)
    before, after = validate_operation(operation, writer.backend)
    current = writer.backend.get(operation.target_id)
    if current != before and current != after:
        raise OperationConflict('Information diverged from both write snapshots')
    writer.backend._ensure_relations_do_not_reuse_deleted_identity(after)
    event = expected_event(operation, writer.backend)
    saved = writer.events.get(event.event_id)
    if saved is not None and saved != event:
        raise OperationConflict('Event diverged from the planned Information effect')
    if saved is not None and current != after:
        raise OperationConflict('Event exists without the planned Information state')
    return dict(format_version=1, family=JOURNAL, action=ACTION,
                operation_id=operation_id, operation_type=operation.operation_type.value,
                target_id=operation.target_id, previous_revision=operation.previous_revision,
                revision=operation.revision, plan_sha256=operation.execution_plan_hash,
                failed_record_sha256=sha256(writer.operations._path(operation_id).read_bytes()).hexdigest(),
                information_state=('ABSENT' if before is None else 'BEFORE') if current == before else 'AFTER',
                event_state='ABSENT' if saved is None else 'MATCH',
                write_information=current != after, write_event=saved is None,
                previous_resolutions=deepcopy(operation.manual_resolutions))


def _checkpoint(stage):
    """Durable boundaries exercised by process-exit tests."""


def _history(entry):
    return (entry.receipt.get('manual_resolutions', []) if entry.receipt is not None
            else entry.operation.manual_resolutions)


def _decision(entry, resolution_id):
    return next((item for item in _history(entry) if item['resolution_id'] == resolution_id), None)


def retry_failed_information(root, review, *, resolution_id, actor, reason, timestamp):
    """Append authorization and resume; terminal/compacted replay cannot resurrect."""
    if (not isinstance(review, dict) or type(review.get('format_version')) is not int
            or review.get('format_version') != 1 or review.get('family') != JOURNAL):
        raise ValueError('an Information resolution review is required')
    writer = _reader(root)
    opid = review.get('operation_id')
    entry = writer.journal.read(opid)
    if entry is None:
        raise OperationConflict('Information operation is missing')
    decision = dict(resolution_id=resolution_id, action=ACTION, actor=actor, reason=reason,
                    timestamp=timestamp, failed_record_sha256=review.get('failed_record_sha256'),
                    review_sha256=_digest(review))
    kind = OperationType(entry.receipt['operation_type']) if entry.receipt is not None else entry.operation.operation_type
    FilesystemOperationRepository._validate_manual_resolutions(kind, OperationStatus.APPLYING, [decision])
    existing = _decision(entry, resolution_id)
    if existing is not None and existing != decision:
        raise OperationConflict('resolution_id reused with a different review or decision')
    if entry.operation is None and existing is None:
        raise OperationConflict('compacted operation has no matching authorization')
    with ExitStack() as locks:
        locks.enter_context(exclusive_write(writer.backend.persistent_root))
        locks.enter_context(exclusive_write(writer.operations.root))
        writer.events.events_root.mkdir(parents=True, exist_ok=True)
        locks.enter_context(exclusive_write(writer.events.events_root))
        entry = writer.journal.read(opid)
        if entry is None:
            raise OperationConflict('Information operation disappeared before authorization')
        existing = _decision(entry, resolution_id)
        if existing is not None:
            if existing != decision:
                raise OperationConflict('resolution_id reused with a different decision')
            if entry.receipt is not None:
                result = entry.result
            else:
                operation = entry.operation
                if operation.status is OperationStatus.FAILED:
                    raise OperationConflict('retry failed again; a new review and resolution_id are required')
                if operation.status not in {OperationStatus.APPLYING, OperationStatus.COMMITTED}:
                    raise OperationConflict('invalid authorized Information retry state')
                if operation.status is OperationStatus.APPLYING:
                    _scope(root, writer, operation)
                result = writer._resume(operation)
        else:
            if _digest(review_failed_information(root, opid)) != _digest(review):
                raise OperationConflict('Information review changed before authorization')
            operation = replace(entry.operation, status=OperationStatus.APPLYING,
                                manual_resolutions=[*entry.operation.manual_resolutions, decision])
            _checkpoint('before_authorization')
            writer.operations._write(operation, writer.operations._path(opid))
            _checkpoint('after_authorization')
            result = writer._resume(operation)
        _checkpoint('after_commit')
        return dict(status='COMMITTED', resolution_id=resolution_id, operation_id=opid, result=result)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    preview = commands.add_parser('preview')
    preview.add_argument('operation_id')
    retry = commands.add_parser('retry')
    retry.add_argument('--review', type=Path, required=True)
    for name in ('resolution-id', 'actor', 'reason', 'timestamp'):
        retry.add_argument('--' + name, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'preview':
            report = review_failed_information(args.root, args.operation_id)
        else:
            report = retry_failed_information(args.root, decode_json_value(args.review.read_text(encoding='utf-8')),
                resolution_id=args.resolution_id, actor=args.actor, reason=args.reason, timestamp=args.timestamp)
    except READ_ERRORS as exc:
        print(json.dumps(dict(status='BLOCKED', reason=str(exc)), ensure_ascii=False))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
