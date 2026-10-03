"""Explicit project dossier rebuild and read-only status/link resolution."""
import argparse
import json
from pathlib import Path

from core.backend.filesystem import FilesystemBackend
from core.dossiers.projects import DossierConflict, ProjectDossiers
from core.dossiers.reconciliation import DossierReconciler, READ_ERRORS
from core.preflight import check_environment
from core.storage_format import decode_json_value
from core.threads.storage import ThreadStorage


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='Engine root')
    parser.add_argument('--output', type=Path, help='Derived dossiers directory; defaults to memory/dossiers')
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('rebuild', 'status'):
        commands.add_parser(name).add_argument('thread_id')
    commands.add_parser('notes', help='Read human sections and whole-document SHA256').add_argument('thread_id')
    edit = commands.add_parser('edit-notes', help='Replace human sections under an expected document SHA256')
    edit.add_argument('thread_id')
    edit.add_argument('--notes', type=Path, required=True, help='JSON with exactly before and after text')
    edit.add_argument('--expected-document-sha256', required=True)
    resolve = commands.add_parser('resolve')
    resolve.add_argument('information_id')
    resolve.add_argument('--selected-thread')
    reconcile = commands.add_parser('reconcile', help='Inspect all project views; --apply repairs them')
    reconcile.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    persistent, history = args.root / 'memory/persistent', args.root / 'memory/history'
    if args.command == 'rebuild':
        check_environment(args.root)
        backend = FilesystemBackend(persistent, history)
        storage = ThreadStorage(persistent)
    else:
        # Read-only paths must not run repository constructors that mkdir.
        backend = FilesystemBackend.__new__(FilesystemBackend)
        backend.persistent_root, backend.history_root = persistent, history
        backend.pending_delete_root = history / 'pending-delete'
        storage = ThreadStorage.__new__(ThreadStorage)
        storage.persistent_root, storage.threads_root = persistent, persistent / 'threads'
    try:
        dossiers = ProjectDossiers(backend, storage, args.output or args.root / 'memory/dossiers')
        if args.command == 'notes':
            result = dict(status='READ', **dossiers.read_notes(args.thread_id))
        elif args.command == 'edit-notes':
            check_environment(args.root)
            notes = decode_json_value(args.notes.read_text(encoding='utf-8'))
            if not isinstance(notes, dict) or set(notes) != {'before', 'after'}:
                raise DossierConflict('notes JSON must contain exactly before and after')
            result = dossiers.replace_notes(args.thread_id, **notes,
                expected_document_sha256=args.expected_document_sha256)
        elif args.command == 'resolve':
            result = dossiers.resolve(args.information_id, selected_thread=args.selected_thread)
        elif args.command == 'reconcile':
            reconciler = DossierReconciler(dossiers)
            if args.apply:
                check_environment(args.root)
            result = reconciler.apply() if args.apply else reconciler.inspect()
        else:
            result = getattr(dossiers, args.command)(args.thread_id)
    except READ_ERRORS as exc:
        print(json.dumps({'status': 'BLOCKED', 'reason': str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(result['status'] in {'STALE', 'REVIEW', 'UNASSIGNED', 'MISSING', 'DRIFT', 'BLOCKED'})


if __name__ == '__main__':
    raise SystemExit(main())
