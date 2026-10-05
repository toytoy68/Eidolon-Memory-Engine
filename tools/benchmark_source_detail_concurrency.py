# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tools/benchmark_source_detail_concurrency.py
# Description : Measure concurrent synthetic detail acceptances without changing production writers.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Measure concurrent synthetic detail acceptances without changing production writers."""
import argparse
from hashlib import sha256
import json
import multiprocessing
from pathlib import Path
import platform
import statistics
import subprocess
import tempfile
from time import perf_counter

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.information.write_audit import audit_information_writes
from core.information.writes import FilesystemInformationWrites
from core.operations.readiness import check_readiness
from core.persistence import has_symlink_component
from core.sources.store import SourceStore
from core.sources import validation
from core.sources.validation import accept_detail
from tools.benchmark_source_details import STAMP
from tools.vm_acceptance import hashes


def accept_worker(root, draft, index, shared, barrier, output):
    try:
        barrier.wait(timeout=20)
        detail = draft['detail'] + (' ' * index if shared else f' #{index}')
        started = perf_counter()
        result = accept_detail(root, dict(draft, model=f'synthetic-{index}'),
                               detail=detail, actor=f'synthetic-{index}')
        output.put(dict(ok=True, information_id=result['information_id'], seconds=perf_counter()-started))
    except Exception as exc:
        output.put(dict(ok=False, error=type(exc).__name__))


def run(*, sizes=(0, 100, 300), replicas=3, workers=4, temp_parent=None):
    sizes = tuple(sizes)
    if (not sizes or any(type(n) is not int or n < 0 for n in sizes)
            or type(replicas) is not int or replicas < 1
            or type(workers) is not int or not 2 <= workers <= 8):
        raise ValueError('nonnegative sizes, positive replicas and 2–8 workers required')
    if 'fork' not in multiprocessing.get_all_start_methods():
        raise ValueError('fork required for this measurement')
    if temp_parent is not None:
        temp_parent = Path(temp_parent).absolute()
        if not temp_parent.is_dir() or has_symlink_component(temp_parent):
            raise ValueError('temporary parent must be an existing real directory')
    context = multiprocessing.get_context('fork')
    points = []
    for size in sorted(set(sizes)):
        for shared in (True, False):
            for replica in range(replicas):
                with tempfile.TemporaryDirectory(prefix='em-detail-concurrent-', dir=temp_parent) as folder:
                    root = Path(folder)
                    backend = FilesystemBackend(root/'memory/persistent', root/'memory/history')
                    writer = FilesystemInformationWrites(backend)
                    for offset in range(0, size, 100):
                        commands = [dict(kind='CREATE', memory=Memory(f'bench-{i:06}', content=f'Synthetic item {i}').__dict__,
                            operation_id=f'bench-create-{i}', event_id=f'bench-event-{i}', actor='benchmark', timestamp=STAMP)
                            for i in range(offset, min(offset+100, size))]
                        if writer.execute_batch(commands)['status'] != 'COMPLETED':
                            raise RuntimeError('seed batch incomplete')
                    store = SourceStore(root)
                    record = store.add(b'Lina lives in Lyon.', original_name='synthetic.txt',
                        title='Synthetic concurrency', author='benchmark', added_at=STAMP)['source']
                    frozen = store.extract(record['source_id'])['extraction']
                    draft = dict(source_id=record['source_id'], source_sha256=record['sha256'],
                        extraction_sha256=frozen['text_sha256'], extractor=frozen['extractor'],
                        paragraph=1, quote='Lina lives in Lyon.', detail='Lina lives in Lyon.',
                        model='synthetic', model_digest='a'*64, proposed_at=STAMP)
                    protected = {path: digest for path, digest in hashes(root).items()
                                 if path.startswith('memory/sources/') or path.endswith('.md')}
                    barrier, output = context.Barrier(workers+1), context.Queue()
                    children = [context.Process(target=accept_worker,
                        args=(root, draft, i, shared, barrier, output)) for i in range(workers)]
                    try:
                        for child in children:
                            child.start()
                        barrier.wait(timeout=20)
                        started = perf_counter()
                        results = [output.get(timeout=60) for _ in children]
                        for child in children:
                            child.join(20)
                        elapsed = perf_counter()-started
                        if any(child.exitcode != 0 for child in children) or not all(row['ok'] for row in results):
                            raise RuntimeError('concurrent acceptance failed')
                    finally:
                        for child in children:
                            if child.is_alive():
                                child.terminate()
                            if child.pid is not None:
                                child.join(5)
                        output.close()
                        output.join_thread()
                    expected = 1 if shared else workers
                    if len({row['information_id'] for row in results}) != expected:
                        raise RuntimeError('concurrent identity mismatch')
                    if len(backend.list(limit=size+workers+1)) != size+expected:
                        raise RuntimeError('canonical count mismatch')
                    after = hashes(root)
                    if any(after.get(path) != digest for path, digest in protected.items()):
                        raise RuntimeError('source or existing Information changed')
                    if audit_information_writes(root)['issues'] or not check_readiness(root)['ready']:
                        raise RuntimeError('concurrent audit/readiness failed')
                    points.append(dict(history_records=size, shared_identity=shared, replica=replica,
                        workers=workers, parent_elapsed_seconds=elapsed,
                        worker_seconds=sorted(row['seconds'] for row in results),
                        new_objects=expected, audit_issues=0, readiness=True, protected_files_unchanged=True))
    summaries = []
    for size in sorted(set(sizes)):
        for shared in (True, False):
            group = [p for p in points if p['history_records'] == size and p['shared_identity'] == shared]
            summaries.append(dict(history_records=size, shared_identity=shared, replicas=len(group),
                median_parent_elapsed_seconds=statistics.median(p['parent_elapsed_seconds'] for p in group),
                median_slowest_worker_seconds=statistics.median(max(p['worker_seconds']) for p in group)))
    return dict(status='PASS', synthetic=True, python=platform.python_version(), workers=workers,
        tool_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        validation_sha256=sha256(Path(validation.__file__).read_bytes()).hexdigest(),
        points=points, summaries=summaries, limitations=[
            'live unindexed synthetic histories, no local AI or private corpus',
            'worker duration includes lock wait and validation; parent duration includes result collection and joins',
            'startup excluded; barrier release and parent timer are not exactly simultaneous',
            'warm local filesystem, not VM, CPU saturation or isolated disk latency',
            'no throughput guarantee or optimization introduced'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sizes', type=int, nargs='+', default=[0, 100, 300])
    parser.add_argument('--replicas', type=int, default=3)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--temp-parent', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error('output must be new')
    try:
        report = run(sizes=args.sizes, replicas=args.replicas, workers=args.workers, temp_parent=args.temp_parent)
    except ValueError as exc:
        parser.error(str(exc))
    report['source_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2)
        handle.write('\n')
    print(json.dumps({'status': report['status'], 'points': len(report['points']), 'synthetic': True}))


if __name__ == '__main__':
    main()
