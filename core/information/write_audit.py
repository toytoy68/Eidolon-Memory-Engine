"""Read-only logical journal audit; use a stopped copy for a stable snapshot."""
import argparse
import json
from pathlib import Path

from core.backend.errors import BackendError
from core.events.errors import EventRepositoryError
from core.events.filesystem import FilesystemEventRepository
from core.information.write_journal import InformationWriteJournal, event_hash, JOURNAL
from core.operations.errors import OperationRepositoryError
from core.operations.models import OperationStatus
from core.persistence import has_symlink_component


def audit_information_writes(engine_root):
    root = Path(engine_root)
    report = {'records': {}, 'issues': []}
    journal = InformationWriteJournal(root / 'memory/history')
    events_root = root / 'memory/history/events' / JOURNAL
    events = FilesystemEventRepository.__new__(FilesystemEventRepository)
    events.events_root = events_root
    try:
        if has_symlink_component(root) or has_symlink_component(events_root):
            raise ValueError('symlinked journal root')
        ids = journal.ids()
    except (OSError, ValueError, OperationRepositoryError) as exc:
        report['issues'].append({'operation_id': None, 'reason': type(exc).__name__})
        return report
    for opid in ids:
        try:
            entry = journal.read(opid)
            if entry is None:
                continue
            if entry.receipt is not None:
                event = events.get(entry.receipt['event_id'])
                if event is None or event_hash(event) != entry.receipt['event_sha256']:
                    raise ValueError('Event differs from receipt')
                status = 'COMPACTING' if entry.operation is not None else 'COMPACTED'
                if entry.operation is not None:
                    report['issues'].append({'operation_id': opid, 'reason': 'compaction_requires_resume'})
            else:
                from core.information.writes import expected_event
                from core.backend.filesystem import FilesystemBackend
                status = entry.operation.status.value
                if entry.operation.status is OperationStatus.COMMITTED:
                    if events.get(entry.operation.plan.event_id) != expected_event(entry.operation, FilesystemBackend):
                        raise ValueError('Event differs from committed plan')
                else:
                    report['issues'].append({'operation_id': opid, 'reason': 'requires_recovery_or_review'})
            report['records'][opid] = {'status': status, 'result': entry.result}
        except (OSError, ValueError, TypeError, BackendError, OperationRepositoryError, EventRepositoryError) as exc:
            report['records'][opid] = {'status': 'BLOCKED'}
            report['issues'].append({'operation_id': opid, 'reason': type(exc).__name__})
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args(argv)
    report = audit_information_writes(args.root)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(bool(report['issues']))


if __name__ == '__main__':
    raise SystemExit(main())
