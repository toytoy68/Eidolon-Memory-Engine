# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tools/benchmark_reservation_index.py
# Description : Compare indexed and strict Information reservations on disposable histories.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Compare indexed and strict Information reservations on disposable histories."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess

from tools.benchmark_information_batches import run


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--size', type=int, default=300)
    parser.add_argument('--incoming', type=int, default=50)
    parser.add_argument('--histories', choices=['live', 'compact'], nargs='+', default=['live', 'compact'])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if not 1 <= args.incoming <= 100 or args.size < args.incoming:
        parser.error('1–100 incoming commands and size >= incoming required')
    sources = [[str(path), hashlib.sha256(path.read_bytes()).hexdigest()]
               for path in sorted(Path('core').rglob('*.py'))]
    report = dict(source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                  runtime_core_sha256=hashlib.sha256(json.dumps(sources, separators=(',', ':')).encode()).hexdigest(),
                  python=platform.python_version(),
                  scope='warm local synthetic histories; one measured run per point, no VM/latency guarantee',
                  setup='batch seeding, optional compaction and initial index rebuild excluded and reported separately',
                  instrumentation='journal_reads = strict validation calls; journal_json_opens includes full-byte hashing; final audits excluded',
                  rows=[])
    for history in args.histories:
        for workload in ('create', 'update'):
            for mode in ('single', 'batch'):
                for indexed in (False, True):
                    row = run(args.size, args.incoming, history, workload, mode, reservation_index=indexed)
                    report['rows'].append(row)
                    print(json.dumps(row), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
