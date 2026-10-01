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
    commands.add_parser('recover')
    compact = commands.add_parser('compact')
    compact.add_argument('operation_id')
    args = parser.parse_args(argv)
    check_environment(ENGINE_ROOT)
    writer = FilesystemInformationWrites(FilesystemBackend(PERSISTENT_ROOT, HISTORY_ROOT))
    if args.command == 'compact':
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
