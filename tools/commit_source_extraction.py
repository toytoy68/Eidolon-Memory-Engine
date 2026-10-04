"""Preview or explicitly commit one existing extraction; never a bulk migration."""
import argparse
import json
from pathlib import Path

from core.sources.store import SourceStore
from core.sources.commitments import read


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--id', required=True, dest='identity')
    parser.add_argument('--apply', action='store_true', help='Explicitly engage this extraction')
    args = parser.parse_args(argv)
    try:
        store = SourceStore(args.root)
        if args.apply:
            result = store.commit_extraction(args.identity)
        else:
            store.extraction(args.identity)
            result = dict(status='UNCHANGED' if read(args.root, args.identity) else 'PREVIEW',
                          execution_performed=False)
        result['source_id'] = args.identity
    except (OSError, ValueError, TypeError, KeyError):
        print(json.dumps(dict(status='BLOCKED', reason='extraction commitment unavailable; inspect source audit')))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
