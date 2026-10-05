# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tools/check_source_restore.py
# Description : Check archive restoration of synthetic sources, accepted details and deletion receipts.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Check archive restoration of synthetic sources, accepted details and deletion receipts."""
import argparse
from hashlib import sha256
import json
import multiprocessing
import os
from pathlib import Path
import platform
import tarfile
import tempfile

from core.backend.filesystem import FilesystemBackend
from core.information.deletion_audit import audit_deletions
from core.information.write_audit import audit_information_writes
from core.information.writes import FilesystemInformationWrites
from core.operations.readiness import check_readiness
from core.persistence import has_symlink_component
from core.sources.store import SourceStore
from core.sources.validation import accept_detail
from tools.vm_acceptance import hashes

STAMP = '2026-10-04T12:00:00Z'
ORIGINAL = b'Lina lives in Lyon.\nLina owns a cat.'


def interrupt_acceptance(root, draft):
    # A real process death after durable intention, before Information publication.
    import core.backend.filesystem as filesystem
    filesystem.FilesystemBackend._atomic_write = lambda *args, **kwargs: os._exit(9)
    accept_detail(root, draft, detail='Synthetic interrupted detail.', actor='synthetic')
    os._exit(0)


def run(*, temp_parent=None, pending=False):
    if type(pending) is not bool:
        raise ValueError('pending must be a boolean')
    if pending and 'fork' not in multiprocessing.get_all_start_methods():
        raise ValueError('fork required for interrupted acceptance')
    if temp_parent is not None:
        temp_parent = Path(temp_parent).absolute()
        if not temp_parent.is_dir() or has_symlink_component(temp_parent):
            raise ValueError('temporary parent must be an existing real directory')
    with tempfile.TemporaryDirectory(prefix='em-source-restore-', dir=temp_parent) as folder:
        work = Path(folder)
        source, restored = work/'source', work/'restored'
        backend = FilesystemBackend(source/'memory/persistent', source/'memory/history')
        store = SourceStore(source)
        record = store.add(ORIGINAL, original_name='synthetic.txt', title='Synthetic restore',
                           author='benchmark', added_at=STAMP)['source']
        frozen = store.extract(record['source_id'])['extraction']
        commitment_path = Path('memory/history/source-extractions-v1') / (record['source_id'] + '.json')
        commitment_bytes = (source / commitment_path).read_bytes()
        draft = dict(source_id=record['source_id'], source_sha256=record['sha256'],
            extraction_sha256=frozen['text_sha256'], extractor=frozen['extractor'],
            paragraph=1, quote='Lina lives in Lyon.', detail='Lina lives in Lyon.',
            model='synthetic-no-inference', model_digest='a'*64, proposed_at=STAMP)
        active = accept_detail(source, draft, detail=draft['detail'], actor='synthetic')
        deleted = accept_detail(source, draft, detail='Synthetic detail to delete.', actor='synthetic')
        backend.delete_request(deleted['information_id'], 'synthetic', 'restore test', 1, 'delete-synthetic')
        writer = FilesystemInformationWrites(backend)
        if writer.compact_batch(writer.journal.ids())['status'] != 'COMPLETED':
            raise RuntimeError('compaction incomplete')
        backend.approve_delete(deleted['information_id'], 'delete-synthetic')
        if pending:
            child = multiprocessing.get_context('fork').Process(target=interrupt_acceptance, args=(source, draft))
            try:
                child.start()
                child.join(20)
                if child.exitcode != 9:
                    raise RuntimeError('interruption checkpoint not reached')
            finally:
                if child.is_alive():
                    child.terminate()
                if child.pid is not None:
                    child.join(5)
        if check_readiness(source)['ready'] != (not pending):
            raise RuntimeError('synthetic readiness differs from expected interrupted state')
        before = hashes(source)
        archive = work/'synthetic.tar'
        # Only our freshly created synthetic root is archived; no user paths accepted.
        with tarfile.open(archive, 'w') as handle:
            handle.add(source, arcname='corpus')
        restored.mkdir()
        with tarfile.open(archive, 'r') as handle:
            handle.extractall(restored, filter='data')
        target = restored/'corpus'
        if hashes(source) != before or hashes(target) != before:
            raise RuntimeError('restored file manifest differs')
        if (target / commitment_path).read_bytes() != commitment_bytes:
            raise RuntimeError('extraction commitment differs after restore')
        clone = FilesystemBackend(target/'memory/persistent', target/'memory/history')
        cloned_store = SourceStore(target)
        if cloned_store.read(record['source_id']) != (record, ORIGINAL) or cloned_store.extraction(record['source_id']) != frozen:
            raise RuntimeError('source original/extraction differs')
        if clone.get(active['information_id']) != backend.get(active['information_id']):
            raise RuntimeError('accepted Information differs')
        content = clone.get(active['information_id'])
        if content.provenance['quote'] not in frozen['paragraphs'][content.provenance['paragraph']-1]:
            raise RuntimeError('exact reference lost')
        if pending:
            if check_readiness(target)['ready']:
                raise RuntimeError('restore silently cleared pending operation')
            try:
                accept_detail(target, draft, detail=draft['detail'], actor='other')
            except ValueError as exc:
                if 'readiness' not in str(exc):
                    raise RuntimeError('unexpected pending guard') from exc
            else:
                raise RuntimeError('pending restored operation did not block acceptance')
            if hashes(target) != before:
                raise RuntimeError('blocked acceptance modified restored corpus')
            FilesystemInformationWrites(clone).recover()
            if not check_readiness(target)['ready']:
                raise RuntimeError('explicit recovery left restored corpus blocked')
            pending_result = accept_detail(target, draft, detail='Synthetic interrupted detail. ', actor='other')
            if clone.get(pending_result['information_id']) is None or not check_readiness(target)['ready']:
                raise RuntimeError('explicit recovery did not finish pending Information')
        replay_before = hashes(target)
        replays = [(draft['detail']+' ', active), ('Synthetic detail to delete. ', deleted)]
        if pending:
            replays.append(('Synthetic interrupted detail.  ', pending_result))
        for detail, expected in replays:
            if accept_detail(target, draft, detail=detail, actor='other') != expected:
                raise RuntimeError('restored replay differs')
        if clone.get(deleted['information_id']) is not None:
            raise RuntimeError('deleted Information resurrected')
        if len(clone.list(limit=4)) != 1+int(pending):
            raise RuntimeError('restored Information count differs')
        audits = {'information_writes': audit_information_writes(target), 'deletions': audit_deletions(target)}
        if any(report['issues'] for report in audits.values()) or not check_readiness(target)['ready']:
            raise RuntimeError('restored audit/readiness failed')
        if hashes(target) != replay_before or hashes(source) != before:
            raise RuntimeError('restoration verification/replay modified corpus')
        digest = sha256(json.dumps(before, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        return dict(status='PASS', synthetic=True, python=platform.python_version(),
            files=len(before), manifest_sha256=digest, original_sha256=sha256(ORIGINAL).hexdigest(),
            extraction_preserved=True, extraction_commitment_preserved=True, exact_reference=True, active_objects=1+int(pending),
            restored_pending_operation=pending, explicit_recovery_verified=pending,
            compacted_write_receipts=sum(row['status']=='COMPACTED' for row in audits['information_writes']['records'].values()), deletion_preserved=True,
            replay_unchanged=True, source_unchanged=True, audit_issues=0, readiness=True,
            tool_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
            limitations=['synthetic corpus only; no running service or reboot',
                         'archive created and restored on one local filesystem',
                         'restore itself not interrupted; no disk failure or private backup tested'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--temp-parent', type=Path)
    parser.add_argument('--pending', action='store_true', help='Archive an interrupted acceptance; recover only the restored copy')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error('output must be new')
    try:
        report = run(temp_parent=args.temp_parent, pending=args.pending)
    except ValueError as exc:
        parser.error(str(exc))
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2)
        handle.write('\n')
    print(json.dumps({'status': report['status'], 'synthetic': True, 'files': report['files']}))


if __name__ == '__main__':
    main()
