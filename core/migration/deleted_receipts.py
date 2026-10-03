"""Explicit import of DELETED reservations and opt-in CANCELLED history from a stopped core tree.

Only receipts are copied. Each publication is durable; replay the same source
on interruption. No global transaction, source mutation or implicit deletion.
"""
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
import argparse
import json
import re

from core.backend.errors import BackendError
from core.backend.filesystem import FilesystemBackend
from core.information.references import (
    ensure_information_write_safety, ensure_no_information_links, ensure_no_thread_links,
)
from core.migration.converter import _atomic_bytes
from core.operations.errors import OperationRepositoryError
from core.operations.readiness import check_readiness
from core.persistence import exclusive_write, has_symlink_component

READ_ERRORS = (OSError, ValueError, TypeError, BackendError, OperationRepositoryError)


def _directories(root):
    for path in (root, root / 'memory', root / 'memory/persistent', root / 'memory/history',
                 root / 'memory/history/pending-delete', root / 'memory/persistent/threads'):
        if has_symlink_component(path) or (path.exists() and not path.is_dir()):
            raise ValueError('tree contains a symlink or invalid directory')
    if not (root / 'memory/persistent').is_dir():
        raise ValueError('an initialized memory/persistent directory is required')


def _safe_absence(root, identity):
    persistent = root / 'memory/persistent'
    path = persistent / (identity + '.md')
    if path.exists() or path.is_symlink():
        raise ValueError('deleted identity has a canonical Information')
    ensure_no_thread_links(persistent / 'threads', identity)
    ensure_no_information_links(persistent, identity, FilesystemBackend._deserialize)
    ensure_information_write_safety(root / 'memory/history', identity, require_compacted=True)


def _safe_cancellation(source, destination, identity, revision):
    """Preserve current bytes; a cancellation does not authorize content transfer."""
    raws = []
    for root in (source, destination):
        path = root / 'memory/persistent' / (identity + '.md')
        if path.is_symlink() or not path.is_file():
            raise ValueError('CANCELLED requires a canonical Information in both trees')
        raw = path.read_bytes()
        memory = FilesystemBackend._deserialize(raw.decode('utf-8'))
        if memory.information_id != identity or memory.revision < revision:
            raise ValueError('canonical Information does not cover cancelled request revision')
        raws.append(raw)
    if raws[0] != raws[1]:
        raise ValueError('CANCELLED canonical Information bytes differ')


def _prepare(source, destination, *, include_cancelled=False):
    source, destination = Path(source).absolute(), Path(destination).absolute()
    report = {'status': 'BLOCKED', 'source': str(source), 'destination': str(destination),
              'receipts': [], 'issues': [], 'scope': ('terminal_deletion_receipts_stopped_source'
                  if include_cancelled else 'deleted_receipts_only_stopped_source')}
    payloads = []
    try:
        # Check links before resolve(), including aliases hiding an overlap.
        _directories(source)
        _directories(destination)
        source, destination = source.resolve(), destination.resolve()
        if (source == destination or source in destination.parents
                or destination in source.parents):
            raise ValueError('source and destination must be separate trees')
        for label, root in (('source', source), ('destination', destination)):
            readiness = check_readiness(root)
            if not readiness['ready']:
                report['issues'].append({'side': label, 'reason': 'readiness_blocked',
                                         'details': readiness['issues']})
        if report['issues']:
            return report, payloads
        directory = source / 'memory/history/pending-delete'
        paths = sorted(directory.iterdir()) if directory.exists() else []
        for path in paths:
            if path.name == '.write.lock' and path.is_file() and not path.is_symlink():
                continue
            try:
                if path.is_symlink() or not path.is_file() or path.suffix != '.json':
                    raise ValueError('unexpected receipt entry')
                if not re.fullmatch(r'[A-Za-z0-9._-]+', path.stem):
                    raise ValueError('invalid Information identity in receipt filename')
                raw = path.read_bytes()
                record = FilesystemBackend._load_delete_request(path, path.stem)
                if path.read_bytes() != raw:
                    raise ValueError('source receipt changed during inspection')
                if record['status'] == 'DELETED':
                    _safe_absence(source, path.stem)
                    _safe_absence(destination, path.stem)
                elif include_cancelled and record['status'] == 'CANCELLED':
                    _safe_cancellation(source, destination, path.stem, record['revision'])
                else:
                    raise ValueError('only terminal DELETED receipts (and opt-in CANCELLED) are supported')
                target = destination / 'memory/history/pending-delete' / path.name
                if target.is_symlink() or (target.exists() and not target.is_file()):
                    raise ValueError('unsafe destination receipt')
                present = target.exists()
                if present and target.read_bytes() != raw:
                    raise ValueError('destination receipt differs; replacement is forbidden')
                report['receipts'].append({'information_id': path.stem, 'revision': record['revision'],
                                          'operation_id': record['operation_id'],
                                          'sha256': sha256(raw).hexdigest(),
                                          'action': 'UNCHANGED' if present else 'IMPORT'})
                if include_cancelled:
                    report['receipts'][-1]['status'] = record['status']
                payloads.append((target, raw, present))
            except READ_ERRORS as exc:
                report['issues'].append({'side': 'receipt', 'file': path.name, 'reason': str(exc)})
        if not report['issues']:
            report['status'] = 'READY' if any(not present for _, _, present in payloads) else 'UNCHANGED'
    except READ_ERRORS as exc:
        report['issues'].append({'side': 'trees', 'reason': str(exc)})
    return report, payloads


def inspect_deleted_receipts(source, destination, *, include_cancelled=False):
    """No mkdir, locks, report files or source changes. No plan is persisted."""
    return (_prepare(source, destination, include_cancelled=True) if include_cancelled
            else _prepare(source, destination))[0]


def _publish_receipt(path, raw):
    from core.operations.read_phase import invalidate_publication
    invalidate_publication(path)
    _atomic_bytes(path, raw)


def import_deleted_receipts(source, destination, *, include_cancelled=False):
    """Validate the entire batch, lock destination, revalidate, then publish.

    Source/legacy writers must be stopped. Existing destination core writers
    coordinate through Persistent and Thread locks; independent low-level journal
    writers are not covered. A failed publication may leave a committed prefix.

    A destination readiness issue seen before the locks may be the in-flight
    publication of a cooperative writer. When the destination writer lock file
    already exists, that issue is only decided under the locks. Tree, source and
    receipt issues, and a destination no cooperative writer ever locked, stay
    immediate: no lock is taken and no lock file is created.
    """
    prepare = (lambda src, dst: _prepare(src, dst, include_cancelled=True)) if include_cancelled else _prepare
    report, _ = prepare(source, destination)
    lock_file = Path(destination) / 'memory/persistent/.write.lock'
    contended = (report['status'] == 'BLOCKED' and bool(report['issues']) and all(
        issue.get('side') == 'destination' and issue.get('reason') == 'readiness_blocked'
        for issue in report['issues']) and lock_file.is_file() and not lock_file.is_symlink())
    if report['status'] != 'READY' and not contended:
        return dict(report, imported=[])
    destination = Path(destination)
    persistent = destination / 'memory/persistent'
    imported = []
    with ExitStack() as locks:
        locks.enter_context(exclusive_write(persistent))
        threads = persistent / 'threads'
        if threads.is_dir():
            locks.enter_context(exclusive_write(threads))
        report, payloads = prepare(source, destination)
        if report['status'] == 'BLOCKED':
            return dict(report, imported=[])
        for target, raw, present in payloads:
            if not present:
                _publish_receipt(target, raw)
                imported.append(target.stem)
        final, _ = prepare(source, destination)
        if final['status'] != 'UNCHANGED':
            return dict(final, status='BLOCKED', imported=imported)
        return dict(final, status='IMPORTED' if imported else 'UNCHANGED', imported=imported)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='Stopped core tree containing memory/')
    parser.add_argument('--destination', type=Path, required=True, help='Initialized destination core tree')
    parser.add_argument('--apply', action='store_true', help='Import validated terminal DELETED receipts')
    parser.add_argument('--include-cancelled', action='store_true',
                        help='Also import exact terminal CANCELLED receipts on matching canonical states')
    args = parser.parse_args(argv)
    try:
        action = import_deleted_receipts if args.apply else inspect_deleted_receipts
        report = (action(args.source, args.destination, include_cancelled=True) if args.include_cancelled
                  else action(args.source, args.destination))
    except READ_ERRORS as exc:
        report = {'status': 'BLOCKED', 'issues': [{'reason': str(exc)}],
                  'retry': 'Publication may have committed a prefix; rerun with the same stopped source.'}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(report['status'] == 'BLOCKED')


if __name__ == '__main__':
    raise SystemExit(main())
