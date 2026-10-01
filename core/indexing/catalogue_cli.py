"""Inspect, rebuild or search the disposable Information metadata catalogue."""
import argparse
import json
from pathlib import Path

from core.backend.errors import BackendError
from core.indexing.catalogue import InformationCatalogue
from core.operations.errors import OperationRepositoryError
from core.threads.storage import ThreadStorageError


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('status')
    commands.add_parser('rebuild')
    query = commands.add_parser('query')
    query.add_argument('text', nargs='?', default='')
    query.add_argument('--limit', type=int, default=20)
    query.add_argument('--project-id')
    query.add_argument('--availability')
    query.add_argument('--epistemic-status')
    args = parser.parse_args(argv)
    try:
        catalogue = InformationCatalogue(args.root)
        if args.command == 'query':
            result = dict(status='CURRENT', items=catalogue.query(
                args.text, limit=args.limit, project_id=args.project_id,
                availability=args.availability, epistemic_status=args.epistemic_status))
        else:
            result = getattr(catalogue, args.command)()
    except (BackendError, OperationRepositoryError, ThreadStorageError, OSError, ValueError, TypeError) as exc:
        print(json.dumps(dict(status='BLOCKED', reason=str(exc)), ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(result['status'] in {'MISSING', 'STALE', 'CORRUPT'})


if __name__ == '__main__':
    raise SystemExit(main())
