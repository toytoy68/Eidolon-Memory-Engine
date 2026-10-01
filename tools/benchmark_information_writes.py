"""Repeatable local journal benchmark, using disposable synthetic data only."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import platform
import subprocess
import tempfile
from time import perf_counter
from unittest.mock import patch

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.information.write_audit import audit_information_writes
from core.information.write_journal import InformationWriteJournal
from core.information.writes import FilesystemInformationWrites


@contextmanager
def count_reads():
    counts = dict(journal_reads=0, journal_scans=0, journal_json_opens=0)
    read, ids, opened = InformationWriteJournal.read, InformationWriteJournal.ids, Path.open
    def count_read(self, *args, **kwargs):
        counts['journal_reads'] += 1
        return read(self, *args, **kwargs)
    def count_ids(self, *args, **kwargs):
        counts['journal_scans'] += 1
        return ids(self, *args, **kwargs)
    def count_open(path, mode='r', *args, **kwargs):
        result = opened(path, mode, *args, **kwargs)
        if ('r' in mode and path.suffix == '.json'
                and path.parent.name == 'information-write-v1'
                and path.parent.parent.name in {'operations', 'operation-receipts'}):
            counts['journal_json_opens'] += 1
        return result
    with patch.object(InformationWriteJournal, 'read', count_read), patch.object(InformationWriteJournal, 'ids', count_ids), patch.object(Path, 'open', count_open):
        yield counts


def benchmark(sizes, mode):
    with tempfile.TemporaryDirectory(prefix='eidolon-journal-benchmark-') as directory:
        root = Path(directory)
        writer = FilesystemInformationWrites(FilesystemBackend(root / 'memory/persistent', root / 'memory/history'))
        rows, originals = [], []
        with count_reads() as counts:
            start = perf_counter()
            for number in range(1, max(sizes) + 1):
                memory = Memory(f'bench-{number:05d}', content='Synthetic measurement ' + str(number),
                                metadata={'type': 'OBSERVATION', 'epistemic_status': 'UNVERIFIED',
                                          'keywords': ['benchmark', 'measurement']})
                originals.append(memory)
                opid = f'write-{number:05d}'
                writer.create(memory, operation_id=opid, event_id=f'event-{number:05d}',
                              actor='benchmark', timestamp='2026-10-01T20:00:00Z')
                if mode == 'create-compact':
                    writer.compact(opid)
                if number in sizes:
                    rows.append(dict(records=number, seconds=round(perf_counter() - start, 6), **counts))
        audit = audit_information_writes(root)
        if audit['issues'] or any(writer.backend.get(m.information_id) != m for m in originals):
            raise RuntimeError('benchmark failed canonical/audit verification')
        return dict(mode=mode, checkpoints=rows, final_audit_issues=0,
                    roundtrip_equal=len(originals))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sizes', type=int, nargs='+', default=[50, 150, 300])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--label', required=True)
    args = parser.parse_args(argv)
    sizes = sorted(set(args.sizes))
    if not sizes or sizes[0] < 1:
        parser.error('positive sizes required')
    report = dict(label=args.label, python=platform.python_version(),
                  source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                  scope='local synthetic warm filesystem; not VM, not a scalability guarantee',
                  instrumentation='logical journal reads, full scans, successful journal JSON read opens; excludes final audits',
                  workloads=[])
    for mode in ('create', 'create-compact'):
        workload = benchmark(sizes, mode)
        report['workloads'].append(workload)
        print(json.dumps(workload), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
