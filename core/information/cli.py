# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/information/cli.py
# Description : Explicit coordinated Information commands (imports use core.migration).
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Explicit coordinated Information commands (imports use core.migration)."""
import argparse
import json
from pathlib import Path

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.config import ENGINE_ROOT, PERSISTENT_ROOT, HISTORY_ROOT
from core.information.writes import FilesystemInformationWrites
from core.preflight import check_environment


def main(argv=None):
    parser = argparse.ArgumentParser(description='Coordinated Information writes and recovery')
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('create', 'update'):
        sub = commands.add_parser(name)
        sub.add_argument('--input', type=Path, required=True, help='Complete Memory JSON')
        sub.add_argument('--operation-id', required=True)
        sub.add_argument('--event-id', required=True)
        sub.add_argument('--actor', required=True)
        sub.add_argument('--timestamp', required=True, help='Stable command timestamp, reused on retry')
        if name == 'update':
            sub.add_argument('--previous-revision', type=int, required=True)
    batch = commands.add_parser('batch')
    batch.add_argument('--input', type=Path, required=True, help='JSON array of 1–100 stable CREATE/UPDATE commands')
    commands.add_parser('index-rebuild', help='Activate or fully rebuild the optional reservation index')
    commands.add_parser('index-status', help='Read-only freshness report; run on a stopped copy')
    compact_batch = commands.add_parser('compact-batch')
    compact_batch.add_argument('--input', type=Path, required=True, help='JSON array of 1–100 distinct operation IDs')
    commands.add_parser('recover')
    compact = commands.add_parser('compact')
    compact.add_argument('operation_id')
    args = parser.parse_args(argv)
    if args.command == 'index-status':
        from core.information.reservation_index import ReservationIndex
        from core.information.batch import ERRORS
        # Avoid writer constructors: inspection must not create journal dirs.
        from core.information.write_journal import InformationWriteJournal
        try:
            result = ReservationIndex(InformationWriteJournal(HISTORY_ROOT)).status()
        except ERRORS as exc:
            result = dict(status='BLOCKED', reason=str(exc))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return int(result['status'] not in {'CURRENT', 'DISABLED'})
    check_environment(ENGINE_ROOT)
    writer = FilesystemInformationWrites(FilesystemBackend(PERSISTENT_ROOT, HISTORY_ROOT))
    if args.command == 'index-rebuild':
        from core.information.batch import ERRORS
        try:
            result = writer.rebuild_reservation_index()
        except ERRORS as exc:
            result = dict(status='BLOCKED', reason=str(exc))
        status = int(result['status'] == 'BLOCKED')
    elif args.command == 'batch':
        from core.information.batch import ERRORS
        from core.storage_format import decode_json_value
        try:
            result = writer.execute_batch(decode_json_value(args.input.read_text(encoding='utf-8')))
        except ERRORS as exc:
            result = dict(status='BLOCKED', error=dict(type=type(exc).__name__, reason=str(exc)))
        status = int(result['status'] == 'BLOCKED')
    elif args.command == 'compact-batch':
        from core.information.batch import ERRORS
        from core.storage_format import decode_json_value
        try:
            result = writer.compact_batch(decode_json_value(args.input.read_text(encoding='utf-8')))
        except ERRORS as exc:
            result = dict(status='BLOCKED', error=dict(type=type(exc).__name__, reason=str(exc)))
        status = int(result['status'] == 'BLOCKED')
    elif args.command == 'compact':
        result = writer.compact(args.operation_id)
        status = 0
    elif args.command == 'recover':
        result = writer.recover()
        status = int(any(value['status'] == 'BLOCKED' for value in result.values()))
    else:
        payload = json.loads(args.input.read_text(encoding='utf-8'))
        memory = Memory(**payload)
        kwargs = dict(operation_id=args.operation_id, event_id=args.event_id,
                      actor=args.actor, timestamp=args.timestamp)
        if args.command == 'update':
            kwargs['previous_revision'] = args.previous_revision
        result = getattr(writer, args.command)(memory, **kwargs)
        status = 0
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return status


if __name__ == '__main__':
    raise SystemExit(main())
