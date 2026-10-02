"""Measure explicit maintenance on disposable synthetic canonical engines."""
import argparse
from collections import Counter
from dataclasses import replace
import json
from pathlib import Path
import platform
import statistics
import subprocess
import tempfile
from time import perf_counter
from unittest.mock import patch

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.information.writes import FilesystemInformationWrites
from core.maintenance.service import MaintenancePass
from core.operations.readiness import check_readiness
from core.threads.models import Thread
from core.threads.storage import ThreadStorage

CREATED = '2026-10-02T03:00:00Z'
DUE = '2026-10-02T08:00:00Z'
SCOPE = {'benchmark': 'maintenance'}


def measure(action, service=None):
    """Successful file read opens, not OS/disk reads; instrumentation adds cost."""
    counts = Counter()
    phases = {}
    opened = Path.open
    started = perf_counter()
    previous_time, previous_counts = started, Counter()
    def count_open(path, mode='r', *args, **kwargs):
        result = opened(path, mode, *args, **kwargs)
        if 'r' in mode:
            if path.suffix == '.json' and 'history' in path.parts:
                counts['history_json_opens'] += 1
            elif path.suffix == '.md' and 'persistent' in path.parts:
                counts['canonical_markdown_opens'] += 1
            elif 'dossiers' in path.parts or 'catalogue' in path.parts:
                counts['derived_read_opens'] += 1
        return result
    def capture(name):
        nonlocal previous_time, previous_counts
        now = perf_counter()
        phases[name] = dict(seconds=round(now - previous_time, 6), reads=dict(counts - previous_counts))
        previous_time, previous_counts = now, counts.copy()
    def checkpoint(stage):
        name = 'readiness_and_recovery' if stage == 'after_recovery' else stage.removeprefix('after_')
        capture(name)
    with patch.object(Path, 'open', count_open):
        if service is None:
            result = action()
        else:
            with patch.object(service, '_checkpoint', checkpoint):
                result = action()
        capture('verification' if service else 'inspection')
    elapsed = round(perf_counter() - started, 6)
    return result, dict(seconds=elapsed, reads=dict(counts), phases=phases)


def summarize(samples):
    times = [sample['seconds'] for sample in samples]
    return dict(median_seconds=round(statistics.median(times), 6),
                min_seconds=min(times), max_seconds=max(times), samples=samples)


def benchmark(size, projects, due_count, repeats, history):
    with tempfile.TemporaryDirectory(prefix='eidolon-maintenance-benchmark-') as directory:
        root = Path(directory)
        backend = FilesystemBackend(root / 'memory/persistent', root / 'memory/history')
        writes = FilesystemInformationWrites(backend)
        originals = []
        setup_start = perf_counter()
        for number in range(size):
            memory = Memory(f'bench-{number:05d}', content=f'Synthetic technical measurement {number}',
                            metadata={'type': 'OBSERVATION', 'epistemic_status': 'CONFIRMED',
                                      'availability': 'LOW', 'keywords': ['synthetic', 'benchmark'],
                                      'qualification': {'version': '0.1', 'nature': 'TECHNICAL', 'qualified_by': 'benchmark'},
                                      'context': {'scope': SCOPE}},
                            provenance={'source': 'synthetic fixture'}, temporal={'observed_at': CREATED})
            originals.append(memory)
            writes.create(memory, operation_id=f'seed-{number}', event_id=f'seed-event-{number}',
                          actor='benchmark', timestamp=CREATED)
            if history == 'compact':
                writes.compact(f'seed-{number}')
        storage = ThreadStorage(backend.persistent_root)
        for number in range(projects):
            members = originals[number::projects]
            storage.create(Thread(f'project-{number}', 'Synthetic project', 'Benchmark only',
                                  relations=[{'type': 'CONCERNS', 'target_id': m.information_id} for m in members],
                                  created_at=CREATED, updated_at=CREATED))
        service = MaintenancePass(root)
        for number, memory in enumerate(originals[:due_count]):
            service.lifecycle.schedule(memory.information_id, revision=1, kind='REACTIVATE', due_at=DUE,
                                       trigger_id=f'wake-{number:05d}', actor='benchmark', created_at=CREATED)
        setup_seconds = round(perf_counter() - setup_start, 6)
        inspected, inspection = measure(lambda: service.inspect(at=CREATED))
        if inspected['status'] != 'READY' or not inspected['work_pending']:
            raise RuntimeError('expected missing projections before initial pass')
        initial, initial_measurement = measure(lambda: service.run(at=CREATED, query_scope=SCOPE), service)
        if initial['status'] != 'COMPLETED' or initial['triggers']:
            raise RuntimeError('initial pass did not rebuild projections without triggering future work')
        idle_samples = []
        for _ in range(repeats):
            result, measured = measure(lambda: service.run(at=CREATED, query_scope=SCOPE), service)
            if (result['status'] != 'COMPLETED' or result['triggers'] or result['dossiers']['actions']
                    or result['catalogue']['status'] != 'UNCHANGED'):
                raise RuntimeError('idle pass unexpectedly mutated business state')
            idle_samples.append(measured)
        due, due_measurement = measure(lambda: service.run(at=DUE, query_scope=SCOPE, limit=due_count), service)
        if (due['status'] != 'COMPLETED' or len(due['triggers']) != due_count
                or any(r['reason'] != 'HIGH' for r in due['triggers'].values())):
            raise RuntimeError('due pass did not apply exactly the expected effects')
        replay_samples = []
        for _ in range(repeats):
            result, measured = measure(lambda: service.run(at=DUE, query_scope=SCOPE), service)
            if (result['status'] != 'COMPLETED' or result['triggers'] or result['dossiers']['actions']
                    or result['catalogue']['status'] != 'UNCHANGED'):
                raise RuntimeError('replay unexpectedly repeated an effect')
            replay_samples.append(measured)
        # Untimed independent semantic checks, beyond the pass's own assertions.
        for number, memory in enumerate(originals):
            expected = (replace(memory, revision=2, metadata=dict(memory.metadata, availability='HIGH'))
                        if number < due_count else memory)
            if backend.get(memory.information_id) != expected:
                raise RuntimeError('canonical content, meaning or revision changed unexpectedly')
        if not check_readiness(root)['ready'] or service.inspect(at=DUE)['work_pending']:
            raise RuntimeError('final readiness or derived freshness failed')
        return dict(records=size, projects=projects, due_count=due_count, history=history,
                    setup_seconds=setup_seconds, inspect_missing=inspection, initial=initial_measurement,
                    idle=summarize(idle_samples), due=due_measurement, replay=summarize(replay_samples),
                    verified_canonical_objects=size, final_ready=True, final_derived_current=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sizes', type=int, nargs='+', default=[50, 150, 300])
    parser.add_argument('--projects', type=int, default=5)
    parser.add_argument('--due-count', type=int, default=5)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--history', nargs='+', choices=['live', 'compact'], default=['live', 'compact'])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    sizes = sorted(set(args.sizes))
    if min(*sizes, args.projects, args.due_count, args.repeats) < 1 or args.projects > min(sizes) or args.due_count > min(sizes):
        parser.error('positive counts required; projects and due-count cannot exceed smallest size')
    report = dict(source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                  python=platform.python_version(), platform=platform.platform(), repeats=args.repeats,
                  scope='local synthetic warmed filesystem; no VM, cold-cache or load guarantee',
                  instrumentation='successful Path.open reads, not physical disk I/O; phase clock includes instrumentation',
                  setup='canonical Information writer history; fixture Threads via direct storage, outside timing',
                  workloads=[])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for history in args.history:
        for size in sizes:
            row = benchmark(size, args.projects, args.due_count, args.repeats, history)
            report['workloads'].append(row)
            args.output.write_text(json.dumps(report, indent=2) + '\n')
            print(json.dumps(dict(records=size, history=history, idle_median=row['idle']['median_seconds'],
                                  due_seconds=row['due']['seconds'], replay_median=row['replay']['median_seconds'])), flush=True)


if __name__ == '__main__':
    main()
