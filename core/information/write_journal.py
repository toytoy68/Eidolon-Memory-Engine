"""Read Information plans and compact receipts as one logical journal.

The reader never creates directories or lock files. Live callers hold the
Persistent/Operation locks; offline audits operate on a stopped data copy.
"""
from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from types import MappingProxyType

from core.operations.errors import OperationConflict
from core.operations.filesystem import FilesystemOperationRepository
from core.operations.models import OperationRecord, OperationStatus
from core.persistence import has_symlink_component
from core.storage_format import decode_json_value


JOURNAL = 'information-write-v1'
RECEIPT_FIELDS = {'format_version', 'status', 'operation_id', 'operation_type', 'target_id',
                  'previous_revision', 'revision', 'event_id', 'command_fingerprint',
                  'plan_hash', 'event_sha256', 'result', 'compacted_at'}


def event_hash(event):
    from core.events.filesystem import FilesystemEventRepository
    from core.information.writes import canonical_json
    return hashlib.sha256(canonical_json(FilesystemEventRepository._to_dict(event)).encode('utf-8')).hexdigest()


def receipt_for(operation, event, compacted_at):
    from core.information.writes import operation_result
    return dict(format_version=1, status='COMMITTED', operation_id=operation.operation_id,
                operation_type=operation.operation_type.value, target_id=operation.target_id,
                previous_revision=operation.previous_revision, revision=operation.revision,
                event_id=operation.plan.event_id, command_fingerprint=operation.plan.command_fingerprint,
                plan_hash=operation.execution_plan_hash, event_sha256=event_hash(event),
                result=operation_result(operation), compacted_at=compacted_at)


@dataclass(frozen=True)
class JournalEntry:
    operation: OperationRecord | None
    receipt: dict | None

    @property
    def result(self):
        from core.information.writes import operation_result
        return self.receipt['result'] if self.receipt is not None else operation_result(self.operation)

    @property
    def fingerprint(self):
        return (self.receipt['command_fingerprint'] if self.receipt is not None
                else self.operation.plan.command_fingerprint)


@dataclass(frozen=True)
class JournalReservations:
    """Validated, content-free view valid only within the caller's writer lock.

    Not cached on a writer, persisted, or reused across commands. All receipt
    formats and operation/receipt pairs were checked before constructing it.
    """
    pending_by_target: MappingProxyType
    event_ids: frozenset[str]

    def require_available(self, target_id, excluding=None):
        if self.pending_by_target.get(target_id, frozenset()) - {excluding}:
            raise OperationConflict('recover pending Information operation first')


class InformationWriteJournal:
    def __init__(self, history_root):
        self.operations_root = Path(history_root) / 'operations' / JOURNAL
        self.receipts_root = Path(history_root) / 'operation-receipts' / JOURNAL
        # get/_path are read-only; the repository constructor creates a directory.
        self.operations = FilesystemOperationRepository.__new__(FilesystemOperationRepository)
        self.operations.root = self.operations_root

    def _check_roots(self):
        for root in (self.operations_root, self.receipts_root):
            if has_symlink_component(root) or (root.exists() and not root.is_dir()):
                raise OperationConflict('invalid Information journal directory')

    def ids(self):
        self._check_roots()
        return sorted({p.stem for root in (self.operations_root, self.receipts_root)
                       for p in root.glob('*.json')})

    def reservations(self):
        """One full validated scan; caller holds Persistent through final use."""
        pending, events = {}, set()
        for operation_id in self.ids():
            entry = self.read(operation_id)
            if entry is None:
                raise OperationConflict('Information journal disappeared during locked scan')
            events.add(entry.result['event_id'])
            operation = entry.operation
            if operation is not None and operation.status is not OperationStatus.COMMITTED:
                pending.setdefault(operation.target_id, set()).add(operation.operation_id)
        return JournalReservations(MappingProxyType({key: frozenset(value) for key, value in pending.items()}),
                                   frozenset(events))

    def receipt_path(self, operation_id):
        return self.receipts_root / self.operations._path(operation_id).name

    def _receipt(self, operation_id):
        path = self.receipt_path(operation_id)
        if path.is_symlink():
            raise OperationConflict('compact receipt is a symlink')
        if not path.exists():
            return None
        try:
            data = decode_json_value(path.read_text(encoding='utf-8'))
            if (not isinstance(data, dict) or set(data) != RECEIPT_FIELDS
                    or type(data['format_version']) is not int or data['format_version'] != 1
                    or data['status'] != 'COMMITTED' or data['operation_id'] != operation_id
                    or data['operation_type'] not in {'INFORMATION_CREATE', 'INFORMATION_UPDATE'}):
                raise ValueError('unsupported compact receipt format')
            for key in ('target_id', 'event_id'):
                if not isinstance(data[key], str) or not re.fullmatch(r'[A-Za-z0-9._-]+', data[key]):
                    raise ValueError('invalid compact receipt identity')
            for key in ('command_fingerprint', 'plan_hash', 'event_sha256'):
                if not isinstance(data[key], str) or not re.fullmatch(r'[0-9a-f]{64}', data[key]):
                    raise ValueError('invalid compact receipt hash')
            previous, revision = data['previous_revision'], data['revision']
            if (type(previous) is not int or type(revision) is not int
                    or previous < 0 or revision != previous + 1
                    or (data['operation_type'] == 'INFORMATION_CREATE') != (previous == 0)
                    or not isinstance(data['compacted_at'], str) or not data['compacted_at']):
                raise ValueError('invalid compact receipt revision')
            if data['result'] != dict(information_id=data['target_id'], previous_revision=previous,
                                      revision=revision, event_id=data['event_id']):
                raise ValueError('compact receipt result mismatch')
            return data
        except (OSError, UnicodeError, ValueError, TypeError, KeyError) as exc:
            raise OperationConflict('invalid compact receipt') from exc

    def read(self, operation_id):
        self._check_roots()
        operation = self.operations.get(operation_id)
        receipt = self._receipt(operation_id)
        if operation is not None:
            from core.information.writes import validate_operation, expected_event
            from core.backend.filesystem import FilesystemBackend
            validate_operation(operation, FilesystemBackend)
            if receipt is not None:
                expected = receipt_for(operation, expected_event(operation, FilesystemBackend), receipt['compacted_at'])
                if operation.status is not OperationStatus.COMMITTED or receipt != expected:
                    raise OperationConflict('divergent Information operation and receipt')
        if operation is None and receipt is None:
            return None
        return JournalEntry(operation, receipt)
