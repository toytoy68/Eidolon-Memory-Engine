"""Compare individual and bounded compaction on disposable synthetic histories."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import platform
import socket
import subprocess
import tempfile
from time import perf_counter

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.information.batch import MAX_BATCH_SIZE
from core.information.write_audit import audit_information_writes
from core.information.writes import FilesystemInformationWrites
from core.persistence import has_symlink_component
from tools.benchmark_information_batches import command
from tools.benchmark_information_writes import count_reads


def benchmark(size, mode, parent=None):
    with tempfile.TemporaryDirectory(prefix='em-compaction-', dir=parent) as directory:
        root = Path(directory)
        writer = FilesystemInformationWrites(FilesystemBackend(root/'memory/persistent', root/'memory/history'))
        started = perf_counter()
        for offset in range(0, size, MAX_BATCH_SIZE):
            result = writer.execute_batch([command(number) for number in range(offset, min(size, offset+MAX_BATCH_SIZE))])
            if result['status'] != 'COMPLETED':
                raise RuntimeError('seeding failed: ' + str(result))
        seed_seconds = perf_counter() - started
        identities = [f'create-{number:05d}' for number in range(size)]
        with count_reads() as counts:
            started = perf_counter()
            if mode == 'single':
                for identity in identities:
                    writer.compact(identity)
            else:
                for offset in range(0, size, MAX_BATCH_SIZE):
                    result = writer.compact_batch(identities[offset:offset+MAX_BATCH_SIZE])
                    if result['status'] != 'COMPLETED':
                        raise RuntimeError('compaction failed: ' + str(result))
            seconds = perf_counter() - started
        first_counts = dict(counts)
        # Independent semantic verification outside the timed work.
        audit = audit_information_writes(root)
        if audit['issues'] or len(audit['records']) != size:
            raise RuntimeError('compaction audit failed')
        if any(record['status'] != 'COMPACTED' for record in audit['records'].values()):
            raise RuntimeError('a full snapshot remains')
        for number in range(size):
            expected = Memory(**command(number)['memory'])
            if writer.backend.get(expected.information_id) != expected:
                raise RuntimeError('canonical value differs after compaction')
            receipt = writer.journal.read(identities[number])
            if receipt.result != writer.create(expected, **{key:value for key,value in command(number).items()
                                                          if key not in {'kind','memory'}}):
                raise RuntimeError('exact command replay differs')
            if expected.content in writer.journal.receipt_path(identities[number]).read_text():
                raise RuntimeError('compact receipt retained canonical content')
        with count_reads() as replay_counts:
            started = perf_counter()
            for offset in range(0, size, MAX_BATCH_SIZE):
                result = writer.compact_batch(identities[offset:offset+MAX_BATCH_SIZE])
                if result['status'] != 'COMPLETED':
                    raise RuntimeError('compaction replay failed')
            replay_seconds = perf_counter() - started
        return dict(records=size, mode=mode, seed_seconds=round(seed_seconds,6),
                    seconds=round(seconds,6), total_preparation_seconds=round(seed_seconds+seconds,6),
                    **first_counts, replay_seconds=round(replay_seconds,6),
                    replay_counts=dict(replay_counts), canonical_verified=size,
                    final_audit_issues=0, full_snapshots_remaining=0)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sizes', type=int, nargs='+', default=[300,1000])
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--temp-parent', type=Path, help='Existing dedicated temporary parent on the chosen filesystem')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    sizes = sorted(set(args.sizes))
    if not sizes or sizes[0] < 1 or args.repeats < 1:
        parser.error('positive sizes and repetition count required')
    if args.temp_parent is not None and (has_symlink_component(args.temp_parent) or not args.temp_parent.is_dir()):
        parser.error('temporary parent must be an existing directory without symlinks')
    sources = [[str(path),sha256(path.read_bytes()).hexdigest()] for path in sorted(Path('core').rglob('*.py'))]
    report = dict(source_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                  runtime_core_sha256=sha256(json.dumps(sources,separators=(',',':')).encode()).hexdigest(),
                  python=platform.python_version(),hostname=socket.gethostname(),
                  scope='synthetic warmed filesystem; successful read opens, not physical disk I/O or a production guarantee',
                  temporary_parent=str(args.temp_parent) if args.temp_parent else tempfile.gettempdir(),
                  repeats=args.repeats, batch_limit=MAX_BATCH_SIZE, rows=[])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    for repeat in range(1,args.repeats+1):
        for size in sizes:
            for mode in ('single','batch'):
                print(json.dumps(dict(status='START',repeat=repeat,records=size,mode=mode)),flush=True)
                row=benchmark(size,mode,args.temp_parent)
                row['independent_repetition']=repeat
                report['rows'].append(row)
                args.output.write_text(json.dumps(report,indent=2)+'\n')
                print(json.dumps(row),flush=True)
    report['completed']=True
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
