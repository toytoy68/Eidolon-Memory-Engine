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


def compact_locked(writer, operation_id):
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
    writer._pending(operation.target_id, excluding=operation_id)
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
