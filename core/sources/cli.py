# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/sources/cli.py
# Description : Explicit source preservation/extraction; never infer or accept details silently.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Explicit source preservation/extraction; never infer or accept details silently."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from core.sources.store import SourceStore, MAX_BYTES


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('list')
    upload = commands.add_parser('add')
    upload.add_argument('--file', type=Path, required=True)
    upload.add_argument('--title', required=True)
    upload.add_argument('--author', default='')
    upload.add_argument('--at', help='Addition timestamp with timezone; defaults to current UTC')
    commands.add_parser('extract').add_argument('source_id')
    args = parser.parse_args(argv)
    try:
        store = SourceStore(args.root)
        if args.command == 'list':
            result = dict(status='READ', sources=store.list())
        elif args.command == 'extract':
            result = store.extract(args.source_id)
        else:
            if args.file.is_symlink() or not args.file.is_file() or args.file.stat().st_size > MAX_BYTES:
                raise ValueError('source file is unsafe or exceeds 10 MiB')
            with args.file.open('rb') as file:
                content = file.read(MAX_BYTES+1)
            result = store.add(content, original_name=args.file.name, title=args.title,
                author=args.author, added_at=args.at or datetime.now(timezone.utc).isoformat())
    except (OSError, ValueError, TypeError, KeyError) as exc:
        result = dict(status='BLOCKED', reason=str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(result['status'] == 'BLOCKED')


if __name__ == '__main__':
    raise SystemExit(main())
