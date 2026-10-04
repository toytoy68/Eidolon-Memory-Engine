"""Measure source-detail acceptance/replay on disposable synthetic live histories."""
import argparse
from contextlib import contextmanager
from hashlib import sha256
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
from core.information.write_audit import audit_information_writes
from core.information.writes import FilesystemInformationWrites
from core.operations.readiness import check_readiness
from core.persistence import has_symlink_component
from core.sources.store import SourceStore
from core.sources import validation
from core.sources.validation import accept_detail
from core.information.write_journal import InformationWriteJournal
from tools.vm_acceptance import hashes

STAMP = '2026-10-04T12:00:00Z'


@contextmanager
def count_work():
    """Counts successful read opens and materialized backend.list results, not bytes."""
    opened, listed = Path.open, FilesystemBackend.list
    counts = dict(markdown_read_opens=0, backend_list_calls=0, backend_list_items=0)
    journal = dict(journal_reads=0, journal_scans=0, journal_json_opens=0)
    read, ids = InformationWriteJournal.read, InformationWriteJournal.ids

    def count_read(self, *args, **kwargs):
        journal['journal_reads'] += 1
        return read(self, *args, **kwargs)

    def count_ids(self, *args, **kwargs):
        journal['journal_scans'] += 1
        return ids(self, *args, **kwargs)

    def count_open(path, mode='r', *args, **kwargs):
        handle = opened(path, mode, *args, **kwargs)
        if 'r' in mode and path.suffix == '.md':
            counts['markdown_read_opens'] += 1
        if ('r' in mode and path.suffix == '.json' and path.parent.name == 'information-write-v1'
                and path.parent.parent.name in {'operations', 'operation-receipts'}):
            journal['journal_json_opens'] += 1
        return handle

    def count_list(self, *args, **kwargs):
        result = listed(self, *args, **kwargs)
        counts['backend_list_calls'] += 1
        counts['backend_list_items'] += len(result)
        return result

    with patch.object(InformationWriteJournal, 'read', count_read), patch.object(InformationWriteJournal, 'ids', count_ids), patch.object(Path, 'open', count_open), patch.object(FilesystemBackend, 'list', count_list):
        yield counts, journal


def run(*, sizes=(0, 100, 300), replicas=3, temp_parent=None):
    sizes = tuple(sizes)
    if (not sizes or any(type(n) is not int or n < 0 for n in sizes)
            or type(replicas) is not int or replicas < 1):
        raise ValueError('nonnegative sizes and positive replicas required')
    if temp_parent is not None:
        temp_parent = Path(temp_parent).absolute()
        if not temp_parent.is_dir() or has_symlink_component(temp_parent):
            raise ValueError('temporary parent must be an existing real directory')
    points = []
    for size in sorted(set(sizes)):
        for replica in range(replicas):
            with tempfile.TemporaryDirectory(prefix='em-detail-bench-', dir=temp_parent) as folder:
                root = Path(folder)
                backend = FilesystemBackend(root/'memory/persistent', root/'memory/history')
                writer = FilesystemInformationWrites(backend)
                start = perf_counter()
                for offset in range(0, size, 100):
                    commands = [dict(kind='CREATE', memory=Memory(f'bench-{i:06}', content=f'Synthetic item {i}').__dict__,
                        operation_id=f'bench-create-{i}', event_id=f'bench-event-{i}', actor='benchmark', timestamp=STAMP)
                        for i in range(offset, min(offset+100, size))]
                    if writer.execute_batch(commands)['status'] != 'COMPLETED':
                        raise RuntimeError('seed batch incomplete')
                store = SourceStore(root)
                record = store.add(b'Lina lives in Lyon.', original_name='synthetic.txt',
                    title='Synthetic measurement', author='benchmark', added_at=STAMP)['source']
                extraction = store.extract(record['source_id'])['extraction']
                draft = dict(source_id=record['source_id'], source_sha256=record['sha256'],
                    extraction_sha256=extraction['text_sha256'], extractor=extraction['extractor'],
                    paragraph=1, quote='Lina lives in Lyon.', detail='Lina lives in Lyon.',
                    model='synthetic-no-inference', model_digest='a'*64, proposed_at=STAMP)
                setup_seconds = perf_counter()-start
                if not check_readiness(root)['ready']:
                    raise RuntimeError('seed not ready')
                first = None
                for mode in ('new', 'replay_variant'):
                    before = hashes(root)
                    with count_work() as (work, journal):
                        start = perf_counter()
                        result = accept_detail(root, draft, detail=draft['detail'] + ('  ' if first else ''),
                                               actor='other' if first else 'benchmark')
                        seconds = perf_counter()-start
                    unchanged = hashes(root) == before
                    if first is None:
                        first = result
                        if unchanged or not result['information_id'].startswith('source-detail-v2-'):
                            raise RuntimeError('new acceptance missing')
                    elif result != first or not unchanged:
                        raise RuntimeError('replay changed identity or corpus')
                    audit = audit_information_writes(root)
                    ready = check_readiness(root)['ready']
                    objects = backend.list(limit=size+2)
                    if audit['issues'] or not ready or len(objects) != size+1:
                        raise RuntimeError('canonical/audit verification failed')
                    if any(backend.get(f'bench-{i:06}') != Memory(f'bench-{i:06}', content=f'Synthetic item {i}') for i in range(size)):
                        raise RuntimeError('existing Information changed')
                    points.append(dict(history_records=size, replica=replica, mode=mode,
                        seconds=seconds, setup_seconds=setup_seconds, **work, **journal,
                        files_unchanged=unchanged, audit_issues=0, readiness=True,
                        canonical_objects=len(objects)))
    summaries = []
    for size in sorted(set(sizes)):
        for mode in ('new', 'replay_variant'):
            group = [p for p in points if p['history_records'] == size and p['mode'] == mode]
            summaries.append(dict(history_records=size, mode=mode, measurements=len(group),
                median_seconds=statistics.median(p['seconds'] for p in group),
                min_seconds=min(p['seconds'] for p in group), max_seconds=max(p['seconds'] for p in group),
                counts={key: sorted({p[key] for p in group}) for key in (
                    'markdown_read_opens', 'backend_list_calls', 'backend_list_items',
                    'journal_reads', 'journal_scans', 'journal_json_opens')}))
    return dict(status='PASS', synthetic=True, python=platform.python_version(),
        temp_parent=str(temp_parent) if temp_parent else tempfile.gettempdir(),
        tool_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        validation_sha256=sha256(Path(validation.__file__).read_bytes()).hexdigest(),
        points=points, summaries=summaries, limitations=[
            'live unindexed histories; unrelated Information, no historical v1 match',
            'single sequential operation per mode on each fresh replica; replay follows new acceptance',
            'warm synthetic filesystem, not VM or isolated disk latency',
            'counts include readiness and writer work; opens are not unique files or bytes',
            'setup, hashing, verification and final audits excluded from measured duration',
            'no local AI call, real corpus, concurrency or throughput guarantee'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sizes', type=int, nargs='+', default=[0, 100, 300])
    parser.add_argument('--replicas', type=int, default=3)
    parser.add_argument('--temp-parent', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error('output must be new')
    try:
        report = run(sizes=args.sizes, replicas=args.replicas, temp_parent=args.temp_parent)
    except ValueError as exc:
        parser.error(str(exc))
    report['source_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    print(json.dumps(dict(status=report['status'], measurements=len(report['points']), synthetic=True)))


if __name__ == '__main__':
    main()
