# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/migration/write_receipts.py
# Description : Import terminal Information replay receipts with exact Events, never canonical bodies.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Import terminal Information replay receipts with exact Events, never canonical bodies.

Source/legacy writers must be stopped. Destination core writers share the locks.
All candidates are validated before the first Event/receipt publication.
"""
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
import argparse
import json

from core.backend.filesystem import FilesystemBackend
from core.events.filesystem import FilesystemEventRepository
from core.events.models import EventType, RelationType
from core.events.errors import EventRepositoryError
from core.information.write_journal import InformationWriteJournal, JOURNAL, event_hash
from core.migration.converter import _atomic_bytes
from core.migration.deleted_receipts import _directories, READ_ERRORS as TREE_ERRORS
from core.operations.errors import OperationRepositoryError
from core.operations.readiness import check_readiness
from core.persistence import exclusive_write, has_symlink_component

READ_ERRORS = (*TREE_ERRORS, EventRepositoryError)


def _events(root):
    reader = FilesystemEventRepository.__new__(FilesystemEventRepository)
    reader.events_root = root / 'memory/history/events' / JOURNAL
    if has_symlink_component(reader.events_root) or (
            reader.events_root.exists() and not reader.events_root.is_dir()):
        raise ValueError('unsafe Information Event directory')
    return reader


def _canonical_state(source, destination, identity, minimum_revision):
    paths = [root / 'memory/persistent' / (identity + '.md') for root in (source, destination)]
    raws = []
    for path in paths:
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError('unsafe canonical Information')
        raw = path.read_bytes() if path.exists() else None
        if raw is not None:
            memory = FilesystemBackend._deserialize(raw.decode('utf-8'))
            if memory.information_id != identity:
                raise ValueError('canonical Information identity mismatch')
            if memory.revision < minimum_revision:
                raise ValueError('canonical Information predates terminal replay receipt')
        raws.append(raw)
    if raws[0] != raws[1]:
        raise ValueError('canonical Information bytes differ; replay-only import cannot change them')
    if raws[0] is None:
        receipts = []
        for root in (source, destination):
            path = root / 'memory/history/pending-delete' / (identity + '.json')
            record = FilesystemBackend._load_delete_request(path, identity)
            if record['status'] != 'DELETED':
                raise ValueError('absent Information requires a terminal DELETED reservation')
            receipts.append(path.read_bytes())
        if receipts[0] != receipts[1]:
            raise ValueError('DELETED reservation differs between trees')


def _exact_target(path, raw):
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError('unsafe destination journal entry')
    present = path.exists()
    if present and path.read_bytes() != raw:
        raise ValueError('destination bytes differ; replacement is forbidden')
    return present


def _prepare(source, destination):
    source, destination = Path(source).absolute(), Path(destination).absolute()
    report = dict(status='BLOCKED', source=str(source), destination=str(destination),
                  scope='terminal_information_receipts_and_events_stopped_source', receipts=[], issues=[])
    payloads = []
    try:
        _directories(source); _directories(destination)
        if source == destination or source in destination.parents or destination in source.parents:
            raise ValueError('source and destination must be separate trees')
        journals = [InformationWriteJournal(root / 'memory/history') for root in (source, destination)]
        src, dst = journals
        for journal in journals:
            journal._check_roots()
        source_events, destination_events = _events(source), _events(destination)
        for side, root in (('source', source), ('destination', destination)):
            state = check_readiness(root)
            if not state['ready']:
                report['issues'].append(dict(side=side, reason='readiness_blocked', details=state['issues']))
        if report['issues']:
            return report, payloads
        destination_entries = {opid:dst.read(opid) for opid in dst.ids()}
        seen_events = set()
        for opid in src.ids():
            try:
                entry = src.read(opid)
                if entry is None or entry.operation is not None or entry.receipt is None:
                    raise ValueError('compact all source Information operations before receipt import')
                receipt = entry.receipt
                identity, event_id = receipt['target_id'], receipt['event_id']
                if event_id in seen_events:
                    raise ValueError('multiple source commands reserve one Event identity')
                seen_events.add(event_id)
                event = source_events.get(event_id)
                expected_type = EventType.CREATED if receipt['operation_type'] == 'INFORMATION_CREATE' else EventType.UPDATED
                if (event is None or event_hash(event) != receipt['event_sha256']
                        or event.information_id != identity or event.revision != receipt['revision']
                        or event.event_type is not expected_type
                        or [r.target for r in event.relations if r.type is RelationType.CAUSED_BY] != [opid]):
                    raise ValueError('Event does not match terminal command identity/revision/type/cause')
                _canonical_state(source, destination, identity, receipt['revision'])
                for other_id, other in destination_entries.items():
                    if other_id != opid and other is not None and other.result['event_id'] == event_id:
                        raise ValueError('another destination command reserves this Event')
                if dst.operations.get(opid) is not None:
                    raise ValueError('destination command has a full operation; compact/review separately')
                source_receipt, source_event = src.receipt_path(opid), source_events._path(event_id)
                raw_receipt, raw_event = source_receipt.read_bytes(), source_event.read_bytes()
                if src.read(opid) != entry or source_events.get(event_id) != event:
                    raise ValueError('source changed during inspection')
                target_receipt, target_event = dst.receipt_path(opid), destination_events._path(event_id)
                receipt_present = _exact_target(target_receipt, raw_receipt)
                event_present = _exact_target(target_event, raw_event)
                # Publish Event first: a killed importer leaves an orphan Event,
                # never a replay receipt whose Event is missing.
                payloads.append((opid, target_event, raw_event, event_present,
                                 target_receipt, raw_receipt, receipt_present))
                report['receipts'].append(dict(operation_id=opid, information_id=identity,
                    event_id=event_id, revision=receipt['revision'],
                    receipt_sha256=sha256(raw_receipt).hexdigest(), event_sha256=sha256(raw_event).hexdigest(),
                    action='UNCHANGED' if receipt_present and event_present else 'IMPORT'))
            except READ_ERRORS as exc:
                report['issues'].append(dict(side='receipt', operation_id=opid, reason=str(exc)))
        if not report['issues']:
            report['status'] = 'READY' if any(not row[3] or not row[6] for row in payloads) else 'UNCHANGED'
    except READ_ERRORS as exc:
        report['issues'].append(dict(side='trees', reason=str(exc)))
    return report, payloads


def inspect_write_receipts(source, destination):
    """No mkdir, locks, report files or source writes."""
    return _prepare(source, destination)[0]


def _publish_file(path, raw):
    from core.operations.read_phase import invalidate_publication
    invalidate_publication(path)
    _atomic_bytes(path, raw)


def import_write_receipts(source, destination):
    """Revalidate all candidates under destination locks, then publish exact pairs.

    A killed process may commit a prefix. Replay from the same stopped source;
    unknown temporary residues are blocked by readiness, never automatically removed.
    """
    report, _ = _prepare(source, destination)
    lock_file = Path(destination) / 'memory/persistent/.write.lock'
    # Only a destination readiness issue beside an existing cooperative lock
    # may be transient. Source/tree/receipt problems remain immediate.
    contended = (report['status'] == 'BLOCKED' and bool(report['issues']) and all(
        issue.get('side') == 'destination' and issue.get('reason') == 'readiness_blocked'
        for issue in report['issues']) and lock_file.is_file() and not lock_file.is_symlink())
    if report['status'] != 'READY' and not contended:
        return dict(report, imported=[])
    destination = Path(destination)
    imported = []
    with ExitStack() as locks:
        locks.enter_context(exclusive_write(destination / 'memory/persistent'))
        locks.enter_context(exclusive_write(destination / 'memory/history/operations' / JOURNAL))
        locks.enter_context(exclusive_write(destination / 'memory/history/events' / JOURNAL))
        report, payloads = _prepare(source, destination)
        if report['status'] == 'BLOCKED':
            return dict(report, imported=[])
        for opid, event_path, event_raw, event_present, receipt_path, receipt_raw, receipt_present in payloads:
            if not event_present:
                _publish_file(event_path, event_raw)
            if not receipt_present:
                _publish_file(receipt_path, receipt_raw)
            if not event_present or not receipt_present:
                imported.append(opid)
        final, _ = _prepare(source, destination)
        if final['status'] != 'UNCHANGED':
            return dict(final, status='BLOCKED', imported=imported)
        return dict(final, status='IMPORTED' if imported else 'UNCHANGED', imported=imported)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    try:
        action = import_write_receipts if args.apply else inspect_write_receipts
        report = action(args.source, args.destination)
    except READ_ERRORS as exc:
        report = dict(status='BLOCKED', issues=[dict(reason=str(exc))],
                      retry='A prefix may be committed; rerun with the same stopped source.')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(report['status'] == 'BLOCKED')


if __name__ == '__main__':
    raise SystemExit(main())
