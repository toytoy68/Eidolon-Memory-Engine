"""Explicit recoverable snapshot compaction; callers hold the writer locks."""
from datetime import datetime, timezone
import os

from core.information.write_journal import receipt_for
from core.operations.errors import OperationConflict, OperationNotFound
from core.operations.models import OperationStatus
from core.persistence import atomic_write_text


def sync_directory(path):
    if os.name != 'nt':
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def durable_unlink(path):
    path.unlink()
    sync_directory(path.parent)


def compact_locked(writer, operation_id, *, reservations=None):
    from core.information.writes import expected_event, canonical_json
    entry = writer.journal.read(operation_id)
    if entry is None:
        raise OperationNotFound(operation_id)
    if entry.operation is None:
        # Persist a removal interrupted between unlink and directory fsync.
        sync_directory(writer.operations.root)
        return entry.result
    operation = entry.operation
    if operation.status is not OperationStatus.COMMITTED:
        raise OperationConflict('compaction requires COMMITTED operation')
    if reservations is None:
        writer._pending(operation.target_id, excluding=operation_id)
    else:
        reservations.require_available(operation.target_id, excluding=operation_id)
    if writer._deletion_status(operation.target_id) in {'APPLYING_DELETE', 'DELETED'}:
        raise OperationConflict('compaction blocked by deletion already applying')
    event = expected_event(operation, writer.backend)
    if writer.events.get(operation.plan.event_id) != event:
        raise OperationConflict('compaction requires matching Event')
    if entry.receipt is None:
        path = writer.journal.receipt_path(operation_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Persist newly created directories too, not just the receipt filename.
        sync_directory(path.parent.parent.parent)
        sync_directory(path.parent.parent)
        receipt = receipt_for(operation, event, datetime.now(timezone.utc).isoformat())
        atomic_write_text(path, canonical_json(receipt) + '\n')
    # Mandatory reread and comparison before retiring the only full snapshot.
    checked = writer.journal.read(operation_id)
    if checked is None or checked.receipt is None:
        raise OperationConflict('compact receipt publication missing')
    durable_unlink(writer.operations._path(operation_id))
    return checked.result


def compact_batch(writer, operation_ids):
    """Compact an ordered lot with one reservation view under writer locks.

    The input list remains the caller's durable queue. A blocked item stops the
    lot; earlier compactions are durable and replayable with the same list.
    """
    import re
    from core.information.batch import MAX_BATCH_SIZE, ERRORS
    from core.persistence import exclusive_write
    if (not isinstance(operation_ids, list)
            or not 1 <= len(operation_ids) <= MAX_BATCH_SIZE
            or any(not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z0-9._-]+', identity)
                   for identity in operation_ids)
            or len(set(operation_ids)) != len(operation_ids)):
        raise ValueError('compaction batch requires 1–100 distinct operation identities')
    operation_ids = list(operation_ids)
    for identity in operation_ids:
        writer.operations._path(identity)
    results, reservations = [], None
    with exclusive_write(writer.backend.persistent_root), exclusive_write(writer.operations.root), exclusive_write(writer.events.events_root):
        for index, identity in enumerate(operation_ids):
            try:
                # A receipt-only replay needs no reservation scan, as in compact.
                if reservations is None:
                    entry = writer.journal.read(identity)
                    if entry is not None and entry.operation is not None:
                        reservations = writer._reservations()
                result = compact_locked(writer, identity, reservations=reservations)
            except ERRORS as exc:
                return dict(status='BLOCKED', results=results, next_index=index,
                            total=len(operation_ids), error=dict(operation_id=identity,
                            type=type(exc).__name__, reason=str(exc)))
            results.append(dict(index=index, operation_id=identity, result=result))
    return dict(status='COMPLETED', results=results, next_index=len(operation_ids),
                total=len(operation_ids), error=None)
