# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/maintenance/cli.py
# Description : Inspect or run one explicit maintenance pass; never install a scheduler.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Inspect or run one explicit maintenance pass; never install a scheduler."""
import argparse
import json
from pathlib import Path

from core.maintenance.service import MaintenancePass, ERRORS
from core.storage_format import decode_json_value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('inspect', 'run'):
        action = commands.add_parser(name)
        action.add_argument('--at', required=True)
        if name == 'run':
            action.add_argument('--scope', type=Path, help='Explicit current execution context JSON; absence means unknown')
            action.add_argument('--limit', type=int, default=100, help='Bound due dispatch only; recovery and derived scans are unbounded')
            action.add_argument('--dossier-limit', type=int, choices=range(1, 101), metavar='1..100',
                                help='Bound dossier publications only; scans and catalogue remain complete')
            action.add_argument('--if-idle', action='store_true',
                                help='Defer when a canonical Persistent/Thread writer lock is busy')
    args = parser.parse_args(argv)
    try:
        service = MaintenancePass(args.root)
        result = (service.inspect(at=args.at) if args.command == 'inspect' else service.run(
            at=args.at, query_scope=decode_json_value(args.scope.read_text(encoding='utf-8')) if args.scope else {},
            limit=args.limit, dossier_limit=args.dossier_limit, if_idle=args.if_idle))
    except ERRORS as exc:
        result = dict(status='BLOCKED', error=dict(type=type(exc).__name__, reason=str(exc)))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(result['status'] == 'BLOCKED')


if __name__ == '__main__':
    raise SystemExit(main())
