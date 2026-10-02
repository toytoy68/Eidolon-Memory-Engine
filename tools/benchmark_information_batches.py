"""Compare standalone and bounded writes on identical synthetic histories."""
import argparse
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import tempfile
from time import perf_counter

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.information.batch import MAX_BATCH_SIZE
from core.information.write_audit import audit_information_writes
from core.information.writes import FilesystemInformationWrites
from tools.benchmark_information_writes import count_reads

STAMP = '2026-10-02T07:00:00Z'


def command(number, *, update=False):
    memory = Memory(f'bench-{number:05d}', content=f'Synthetic measurement {number}')
    if update:
        memory = replace(memory, content=f'Updated measurement {number}')
    prefix = 'update' if update else 'create'
    result = dict(kind='UPDATE' if update else 'CREATE', memory=asdict(memory),
                  operation_id=f'{prefix}-{number:05d}', event_id=f'{prefix}-event-{number:05d}',
                  actor='benchmark', timestamp=STAMP)
    if update:
        result['previous_revision'] = 1
    return result


def run(size, incoming, history, workload, mode):
    with tempfile.TemporaryDirectory(prefix='eidolon-batch-benchmark-') as directory:
        root = Path(directory)
        writer = FilesystemInformationWrites(FilesystemBackend(root / 'memory/persistent', root / 'memory/history'))
        setup_started = perf_counter()
        for offset in range(0, size, MAX_BATCH_SIZE):
            seeded = writer.execute_batch([command(i) for i in range(offset, min(offset + MAX_BATCH_SIZE, size))])
            if seeded['status'] != 'COMPLETED':
                raise RuntimeError(seeded)
        if history == 'compact':
            for i in range(size):
                writer.compact(f'create-{i:05d}')
        setup_seconds = round(perf_counter() - setup_started, 6)
        commands = [command(i, update=workload == 'update')
                    for i in (range(incoming) if workload == 'update' else range(size, size + incoming))]
        with count_reads() as counts:
            started = perf_counter()
            if mode == 'batch':
                result = writer.execute_batch(commands)
                if result['status'] != 'COMPLETED':
                    raise RuntimeError(result)
            else:
                for item in commands:
                    kwargs = {key: value for key, value in item.items() if key not in {'memory', 'kind'}}
                    method = writer.update if workload == 'update' else writer.create
                    method(Memory(**item['memory']), **kwargs)
            seconds = round(perf_counter() - started, 6)
        expected = {i: Memory(**command(i)['memory']) for i in range(size)}
        for item in commands:
            memory = Memory(**item['memory'])
            expected[int(memory.information_id.split('-')[1])] = replace(memory, revision=2) if workload == 'update' else memory
        audit = audit_information_writes(root)
        if audit['issues'] or any(writer.backend.get(memory.information_id) != memory for memory in expected.values()):
            raise RuntimeError('benchmark failed canonical/audit verification')
        return dict(history_records=size, incoming=incoming, history=history, workload=workload,
                    mode=mode, seconds=seconds, setup_seconds=setup_seconds, **counts,
                    final_audit_issues=0, canonical_verified=len(expected))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sizes', type=int, nargs='+', default=[0, 100, 300])
    parser.add_argument('--incoming', type=int, default=50)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    sizes = sorted(set(args.sizes))
    if not sizes or sizes[0] < 0 or not 1 <= args.incoming <= MAX_BATCH_SIZE:
        parser.error('nonnegative history sizes and 1–100 incoming commands required')
    sources = [[str(path), hashlib.sha256(path.read_bytes()).hexdigest()]
               for path in sorted(Path('core').rglob('*.py'))]
    digest = hashlib.sha256(json.dumps(sources, separators=(',', ':')).encode())
    report = dict(source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                  runtime_core_sha256=digest.hexdigest(), python=platform.python_version(),
                  scope='local synthetic warm filesystem; one measured run per point, not VM or a throughput guarantee',
                  setup='same histories seeded in batches, optionally compacted; excluded from measurements',
                  instrumentation='logical journal reads, full scans, successful journal JSON read opens; excludes final audits',
                  rows=[])
    for history in ('live', 'compact'):
        for size in sizes:
            for workload in (('create', 'update') if size == max(sizes) and size >= args.incoming else ('create',)):
                for mode in ('single', 'batch'):
                    row = run(size, args.incoming, history, workload, mode)
                    report['rows'].append(row)
                    print(json.dumps(row), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
