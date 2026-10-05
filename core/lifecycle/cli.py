# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/lifecycle/cli.py
# Description : Explicit lifecycle commands; no daemon or system scheduler is installed.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Explicit lifecycle commands; no daemon or system scheduler is installed."""
import argparse
import json
from pathlib import Path

from core.backend.errors import BackendError
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.events.errors import EventRepositoryError
from core.lifecycle.service import AvailabilityService, LifecycleTriggers
from core.operations.errors import OperationRepositoryError
from core.storage_format import decode_json_value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('list')
    commands.add_parser('recover')
    schedule = commands.add_parser('schedule')
    schedule.add_argument('target_id')
    schedule.add_argument('--revision', required=True, type=int)
    schedule.add_argument('--kind', required=True, choices=['REACTIVATE', 'RECHECK'])
    schedule.add_argument('--due-at', required=True)
    schedule.add_argument('--trigger-id', required=True)
    schedule.add_argument('--actor', required=True)
    schedule.add_argument('--at', required=True)
    due = commands.add_parser('run-due')
    due.add_argument('--at', required=True)
    due.add_argument('--scope', type=Path)
    due.add_argument('--limit', type=int, default=100)
    cancel = commands.add_parser('cancel')
    cancel.add_argument('trigger_id')
    cancel.add_argument('--actor', required=True)
    cancel.add_argument('--at', required=True)
    cancel.add_argument('--reason', required=True)
    for name in ('set-level', 'acknowledge-review'):
        operation = commands.add_parser(name)
        operation.add_argument('--memory', required=True, type=Path, help='Original Memory JSON snapshot, preserved for replay')
        operation.add_argument('--operation-id', required=True)
        operation.add_argument('--event-id', required=True)
        operation.add_argument('--actor', required=True)
        operation.add_argument('--at', required=True)
        if name == 'set-level':
            operation.add_argument('--level', required=True, choices=['HIGH', 'INTERMEDIATE', 'LOW'])
    args = parser.parse_args(argv)
    try:
        backend = FilesystemBackend.__new__(FilesystemBackend)
        backend.persistent_root = args.root / 'memory/persistent'
        backend.history_root = args.root / 'memory/history'
        backend.pending_delete_root = backend.history_root / 'pending-delete'
        lifecycle = LifecycleTriggers(backend)
        if args.command == 'list':
            result = {i: lifecycle.journal.read(i) for i in lifecycle.journal.ids()}
        elif args.command == 'schedule':
            result = lifecycle.schedule(args.target_id, revision=args.revision, kind=args.kind,
                due_at=args.due_at, trigger_id=args.trigger_id, actor=args.actor, created_at=args.at)
        elif args.command == 'cancel':
            result = lifecycle.cancel(args.trigger_id, actor=args.actor, at=args.at, reason=args.reason)
        elif args.command == 'run-due':
            scope = decode_json_value(args.scope.read_text()) if args.scope else {}
            result = lifecycle.run_due(at=args.at, query_scope=scope, limit=args.limit)
        elif args.command == 'recover':
            result = lifecycle.recover()
        else:
            memory = Memory(**decode_json_value(args.memory.read_text(encoding='utf-8')))
            service = AvailabilityService(backend)
            command = dict(operation_id=args.operation_id, event_id=args.event_id, actor=args.actor, timestamp=args.at)
            result = (service.set_level(memory, args.level, **command) if args.command == 'set-level'
                      else service.acknowledge_review(memory, **command))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return int(any(isinstance(value, dict) and value.get('status') == 'BLOCKED' for value in result.values()))
    except (OSError, ValueError, TypeError, KeyError, BackendError, OperationRepositoryError, EventRepositoryError) as exc:
        print(json.dumps({'status': 'BLOCKED', 'reason': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
