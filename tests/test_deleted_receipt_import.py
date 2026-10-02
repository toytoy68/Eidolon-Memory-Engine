"""Operational DELETED import preserves the identity reservation, never a body."""
import json
import subprocess
import sys

import pytest

from core.backend.errors import BackendError
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.information.writes import FilesystemInformationWrites
from core.migration.deleted_receipts import inspect_deleted_receipts, import_deleted_receipts, main
from core.operations.errors import OperationConflict
from core.operations.readiness import check_readiness
from core.threads.models import Thread
from core.threads.storage import ThreadStorage
from tests.test_migration_converter import fingerprints

STAMP = '2026-10-02T12:30:00Z'


def seed(tmp_path, count=2):
    source, destination = tmp_path / 'source', tmp_path / 'destination'
    src = FilesystemBackend(source / 'memory/persistent', source / 'memory/history')
    dst = FilesystemBackend(destination / 'memory/persistent', destination / 'memory/history')
    for n in range(count):
        identity = f'deleted-{n}'
        src.store(Memory(identity, content='private body'))
        src.delete_request(identity, 'human', 'remove obsolete data', 1, f'delete-{n}')
        src.approve_delete(identity, f'delete-{n}')
    return source, destination, src, dst


def test_preview_readonly_import_exact_bytes_replay_and_reservation(tmp_path):
    source, destination, src, dst = seed(tmp_path)
    path = src.pending_delete_root / 'deleted-0.json'
    path.write_bytes(path.read_bytes().replace(b'\n', b'\r\n'))
    before = fingerprints(source), fingerprints(destination)
    preview = inspect_deleted_receipts(source, destination)
    assert preview['status'] == 'READY'
    assert len(preview['receipts']) == 2
    assert (fingerprints(source), fingerprints(destination)) == before
    result = import_deleted_receipts(source, destination)
    assert result['status'] == 'IMPORTED' and result['imported'] == ['deleted-0', 'deleted-1']
    assert fingerprints(source) == before[0]
    assert check_readiness(destination)['ready']
    for identity in ('deleted-0', 'deleted-1'):
        assert (dst.pending_delete_root / (identity + '.json')).read_bytes() == (
            src.pending_delete_root / (identity + '.json')).read_bytes()
        assert dst.get(identity) is None
        with pytest.raises(BackendError):
            dst.store(Memory(identity, content='must not resurrect'))
        writes = FilesystemInformationWrites(dst)
        with pytest.raises((BackendError, OperationConflict)):
            writes.create(Memory(identity), operation_id='new-' + identity,
                          event_id='event-' + identity, actor='human', timestamp=STAMP)
    after = fingerprints(destination)
    replay = import_deleted_receipts(source, destination)
    assert replay['status'] == 'UNCHANGED' and replay['imported'] == []
    assert fingerprints(destination) == after
    assert not (destination / 'memory/history/operations/thread-delete-v1').exists()


@pytest.mark.parametrize('change', ['conflict', 'resurrection', 'malformed', 'unknown-version',
                                    'unknown-file', 'receipt-link', 'receipt-directory',
                                    'source-present', 'thread-link', 'information-link',
                                    'corrupt-thread', 'pending-journal'])
def test_all_conflicts_are_found_before_publishing_any_receipt(tmp_path, change):
    source, destination, src, dst = seed(tmp_path)
    path = src.pending_delete_root / 'deleted-1.json'
    if change == 'conflict':
        data = json.loads(path.read_text()); data['reason'] = 'other history'
        (dst.pending_delete_root / path.name).write_text(json.dumps(data))
    elif change == 'resurrection':
        dst.store(Memory('deleted-1', content='already exists'))
    elif change == 'malformed':
        path.write_text('{')
    elif change == 'unknown-version':
        data = json.loads(path.read_text()); data['format_version'] = 999
        path.write_text(json.dumps(data))
    elif change == 'unknown-file':
        (src.pending_delete_root / 'unknown.txt').write_text('unknown')
    elif change == 'receipt-link':
        path.unlink(); path.symlink_to(src.pending_delete_root / 'deleted-0.json')
    elif change == 'receipt-directory':
        path.unlink(); path.mkdir()
    elif change == 'source-present':
        (src.persistent_root / 'deleted-1.md').write_text(FilesystemBackend._serialize(Memory('deleted-1')))
    elif change == 'thread-link':
        storage = ThreadStorage(dst.persistent_root)
        thread = Thread('linked', 'Project', 'Goal',
                        relations=[{'type': 'CONCERNS', 'target_id': 'deleted-1'}])
        # Simulate a legacy orphan link; the current writer rightly forbids it.
        storage._path('linked').write_text(storage._serialize_checked(thread))
    elif change == 'information-link':
        dst.store(Memory('linked', relations=[{'type': 'RELATED_TO', 'target_id': 'deleted-1'}]))
    elif change == 'corrupt-thread':
        storage = ThreadStorage(dst.persistent_root)
        storage._path('broken').write_text('Invalid Thread')
    elif change == 'pending-journal':
        directory = dst.history_root / 'operations/unknown-v1'
        directory.mkdir(parents=True); (directory / 'pending.json').write_text('{}')
    before = fingerprints(source), fingerprints(destination)
    assert inspect_deleted_receipts(source, destination)['status'] == 'BLOCKED'
    result = import_deleted_receipts(source, destination)
    assert result['status'] == 'BLOCKED' and result['imported'] == []
    assert (fingerprints(source), fingerprints(destination)) == before
    assert not (dst.pending_delete_root / 'deleted-0.json').exists()


@pytest.mark.parametrize('status', ['PENDING_DELETE', 'CANCELLED', 'APPLYING_DELETE'])
def test_non_deleted_states_are_never_activated(tmp_path, status):
    source, destination, src, _ = seed(tmp_path)
    identity = 'pending'
    src.store(Memory(identity))
    src.delete_request(identity, 'human', 'review', 1, 'request')
    if status == 'CANCELLED':
        src.cancel_delete(identity, 'request')
    elif status == 'APPLYING_DELETE':
        path = src.pending_delete_root / (identity + '.json')
        data = json.loads(path.read_text()); data.update(status=status, content_sha256='0' * 64)
        path.write_text(json.dumps(data))
    before = fingerprints(source), fingerprints(destination)
    assert import_deleted_receipts(source, destination)['status'] == 'BLOCKED'
    assert (fingerprints(source), fingerprints(destination)) == before


@pytest.mark.parametrize('side', ['source', 'destination'])
def test_symlinked_ancestor_is_refused_without_writes(tmp_path, side):
    source, destination, _, _ = seed(tmp_path)
    alias = tmp_path / 'alias'; alias.symlink_to(source if side == 'source' else destination, target_is_directory=True)
    before = fingerprints(source), fingerprints(destination)
    report = import_deleted_receipts(alias if side == 'source' else source,
                                     alias if side == 'destination' else destination)
    assert report['status'] == 'BLOCKED'
    assert (fingerprints(source), fingerprints(destination)) == before


def test_overlapping_or_uninitialized_trees_are_refused(tmp_path):
    source, destination, _, _ = seed(tmp_path)
    nested = source / 'nested'
    FilesystemBackend(nested / 'memory/persistent', nested / 'memory/history')
    before = fingerprints(tmp_path)
    for target in (source, nested, tmp_path / 'missing'):
        assert import_deleted_receipts(source, target)['status'] == 'BLOCKED'
    assert fingerprints(tmp_path) == before
    assert not (tmp_path / 'missing').exists()


def test_interrupted_prefix_resumes_and_source_is_unchanged(tmp_path, monkeypatch):
    import core.migration.deleted_receipts as module
    source, destination, src, dst = seed(tmp_path)
    before = fingerprints(source)
    publish = module._publish_receipt
    def interrupted(path, raw):
        if path.stem == 'deleted-1':
            raise OSError('disk unavailable')
        publish(path, raw)
    with monkeypatch.context() as patch:
        patch.setattr(module, '_publish_receipt', interrupted)
        with pytest.raises(OSError):
            import_deleted_receipts(source, destination)
    assert (dst.pending_delete_root / 'deleted-0.json').exists()
    assert not (dst.pending_delete_root / 'deleted-1.json').exists()
    assert import_deleted_receipts(source, destination)['imported'] == ['deleted-1']
    assert fingerprints(source) == before


def test_real_process_exit_after_first_publication_is_replayable(tmp_path):
    source, destination, _, dst = seed(tmp_path)
    before = fingerprints(source)
    script = '''
import os, sys
import core.migration.deleted_receipts as m
publish = m._publish_receipt
def stop(path, raw):
    publish(path, raw)
    os._exit(74)
m._publish_receipt = stop
m.import_deleted_receipts(sys.argv[1], sys.argv[2])
'''
    stopped = subprocess.run([sys.executable, '-B', '-c', script, str(source), str(destination)])
    assert stopped.returncode == 74
    assert import_deleted_receipts(source, destination)['imported'] == ['deleted-1']
    assert fingerprints(source) == before
    assert check_readiness(destination)['ready']


def test_cli_preview_apply_and_blocked_exit_codes(tmp_path, capsys):
    source, destination, src, _ = seed(tmp_path)
    args = ['--source', str(source), '--destination', str(destination)]
    before = fingerprints(destination)
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'READY'
    assert fingerprints(destination) == before
    assert main(args + ['--apply']) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'IMPORTED'
    (src.pending_delete_root / 'invalid.json').write_text('{}')
    assert main(args + ['--apply']) == 1
    assert json.loads(capsys.readouterr().out)['status'] == 'BLOCKED'


def test_apply_rechecks_destination_after_obtaining_locks(tmp_path, monkeypatch):
    import core.migration.deleted_receipts as module
    source, destination, _, dst = seed(tmp_path)
    prepare = module._prepare
    count = 0
    def changed(source, target):
        nonlocal count
        count += 1
        if count == 2:
            dst.store(Memory('deleted-1', content='intervening writer'))
        return prepare(source, target)
    monkeypatch.setattr(module, '_prepare', changed)
    result = import_deleted_receipts(source, destination)
    assert result['status'] == 'BLOCKED' and result['imported'] == []
    assert not (dst.pending_delete_root / 'deleted-0.json').exists()
    assert dst.get('deleted-1').content == 'intervening writer'


def test_no_receipts_is_unchanged_without_destination_initialization(tmp_path):
    source, destination, _, _ = seed(tmp_path, count=0)
    before = fingerprints(source), fingerprints(destination)
    assert inspect_deleted_receipts(source, destination)['status'] == 'UNCHANGED'
    assert import_deleted_receipts(source, destination)['imported'] == []
    assert (fingerprints(source), fingerprints(destination)) == before


def test_uncompacted_destination_snapshot_blocks_without_purging_it(tmp_path):
    source, destination, _, dst = seed(tmp_path)
    writes = FilesystemInformationWrites(dst)
    writes.create(Memory('deleted-1', content='retained snapshot'), operation_id='old-write',
                  event_id='old-event', actor='human', timestamp=STAMP)
    dst._path('deleted-1').unlink()  # Simulate a damaged/restored destination.
    before = fingerprints(destination)
    result = import_deleted_receipts(source, destination)
    assert result['status'] == 'BLOCKED'
    assert any('compact' in issue['reason'] for issue in result['issues'])
    assert fingerprints(destination) == before


def test_source_write_receipts_events_and_index_are_not_activated(tmp_path):
    source, destination, src, dst = seed(tmp_path, count=0)
    writes = FilesystemInformationWrites(src)
    writes.create(Memory('deleted-0', content='private history'), operation_id='created',
                  event_id='created-event', actor='human', timestamp=STAMP)
    writes.compact('created')
    writes.rebuild_reservation_index()
    src.delete_request('deleted-0', 'human', 'remove', 1, 'deleted')
    src.approve_delete('deleted-0', 'deleted')
    before = fingerprints(source)
    assert import_deleted_receipts(source, destination)['status'] == 'IMPORTED'
    assert fingerprints(source) == before
    assert not (dst.history_root / 'operations').exists()
    assert not (dst.history_root / 'operation-receipts').exists()
    assert not (dst.history_root / 'events').exists()
    assert not (destination / 'memory/derived').exists()
    assert set(p.name for p in dst.pending_delete_root.iterdir()) == {'deleted-0.json'}


def test_two_processes_import_same_receipts_once(tmp_path):
    from core.persistence import exclusive_write
    source, destination, _, dst = seed(tmp_path)
    script = '''
import json, sys
from core.migration.deleted_receipts import import_deleted_receipts
print('started', flush=True)
print(json.dumps(import_deleted_receipts(sys.argv[1], sys.argv[2])), flush=True)
'''
    processes = []
    with exclusive_write(dst.persistent_root):
        for _ in range(2):
            process = subprocess.Popen([sys.executable, '-B', '-c', script, str(source), str(destination)],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            processes.append(process)
            assert process.stdout.readline().strip() == 'started'
    results = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=20)
        assert process.returncode == 0, stderr
        results.append(json.loads(stdout))
    assert sorted(result['status'] for result in results) == ['IMPORTED', 'UNCHANGED']
    assert sum(len(result['imported']) for result in results) == 2
    assert check_readiness(destination)['ready']


def test_cli_publication_error_reports_replay_requirement(tmp_path, capsys, monkeypatch):
    import core.migration.deleted_receipts as module
    source, destination, _, _ = seed(tmp_path)
    def stop(path, raw):
        raise OSError('disk full')
    monkeypatch.setattr(module, '_publish_receipt', stop)
    assert main(['--source', str(source), '--destination', str(destination), '--apply']) == 1
    report = json.loads(capsys.readouterr().out)
    assert report['status'] == 'BLOCKED' and 'prefix' in report['retry']


def test_exit_before_atomic_rename_leaves_unknown_temp_blocking_review(tmp_path):
    source, destination, _, dst = seed(tmp_path)
    before = fingerprints(source)
    script = '''
import os, sys
import core.migration.converter as converter
from core.migration.deleted_receipts import import_deleted_receipts
converter.os.replace = lambda *args: os._exit(74)
import_deleted_receipts(sys.argv[1], sys.argv[2])
'''
    stopped = subprocess.run([sys.executable, '-B', '-c', script, str(source), str(destination)])
    assert stopped.returncode == 74
    assert not (dst.pending_delete_root / 'deleted-0.json').exists()
    remains = fingerprints(destination)
    report = import_deleted_receipts(source, destination)
    assert report['status'] == 'BLOCKED' and report['imported'] == []
    assert fingerprints(destination) == remains  # Never auto-delete an unknown file.
    assert fingerprints(source) == before
