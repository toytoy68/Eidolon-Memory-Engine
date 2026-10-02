"""Human retries of failed linked creation preserve the original identities."""
from dataclasses import replace
import json
import subprocess
import sys

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.errors import InformationDeletionBlocked
from core.events.filesystem import FilesystemEventRepository
from core.operations.errors import OperationConflict, InvalidOperationRecord
from core.operations.failed_resolution import review_failed_thread, retry_failed_thread, retry_failed_status, main
from core.operations.filesystem import FilesystemOperationRepository
from core.operations.models import OperationStatus
from core.operations.readiness import check_readiness, recover_all
from core.operations.thread_create import FilesystemLinkedThreadCreation
from core.operations.thread_status import plan_hash
from core.threads.models import Thread
from core.threads.storage import ThreadStorage, ThreadStorageError
from core.backend.models import Memory
from tests.test_failed_status_resolution import business_files, seed as seed_status
from tests.test_migration_converter import fingerprints

FAMILY = 'thread-create-v1'
STAMP = '2026-10-03T01:00:00+02:00'


def seed(root, monkeypatch, phase='before', identity='project', opid='create', eventid='event'):
    backend = FilesystemBackend(root / 'memory/persistent', root / 'memory/history')
    if backend.get('one') is None:
        backend.store(Memory('one', content='Source'))
    engine = FilesystemLinkedThreadCreation(backend, ThreadStorage(backend.persistent_root),
        FilesystemEventRepository(backend.history_root / 'events' / FAMILY),
        FilesystemOperationRepository(backend.history_root / 'operations' / FAMILY))
    def stop(*args, **kw):
        raise RuntimeError('stopped')
    with monkeypatch.context() as patch:
        if phase == 'before':
            patch.setattr(engine, '_resume', stop)
        elif phase == 'thread':
            patch.setattr(engine.events, 'save', stop)
        else:
            update = engine.operations.update
            def before_commit(record):
                if record.status is OperationStatus.COMMITTED:
                    stop()
                update(record)
            patch.setattr(engine.operations, 'update', before_commit)
        with pytest.raises(RuntimeError):
            engine.create(Thread(identity, 'Project', 'Goal', created_at=STAMP, updated_at=STAMP),
                          'one', operation_id=opid, event_id=eventid)
    engine.operations.update(replace(engine.operations.get(opid), status=OperationStatus.FAILED))
    return backend, engine


def review(root):
    return review_failed_thread(root, 'create', family=FAMILY)


def retry(root, report, **kw):
    decision = dict(resolution_id='decision', actor='human', reason='Effects reviewed', timestamp=STAMP)
    decision.update(kw)
    return retry_failed_thread(root, report, **decision)


@pytest.mark.parametrize('phase', ['before', 'thread', 'event'])
def test_creation_review_retry_and_terminal_replay(tmp_path, monkeypatch, phase):
    _, engine = seed(tmp_path, monkeypatch, phase)
    failed = engine.operations.get('create'); before = fingerprints(tmp_path)
    report = review(tmp_path)
    assert fingerprints(tmp_path) == before
    assert report['information_id'] == 'one'
    assert report['action'] == 'RETRY_THREAD_CREATE_V1'
    assert report['thread_state'] == ('ABSENT' if phase == 'before' else 'AFTER')
    assert report['write_thread'] == (phase == 'before')
    assert report['event_state'] == ('MATCH' if phase == 'event' else 'ABSENT')
    assert recover_all(tmp_path)['passes'] == 0
    result = retry(tmp_path, report)
    completed = engine.operations.get('create')
    assert completed.status is OperationStatus.COMMITTED
    assert completed.plan == failed.plan and plan_hash(completed) == failed.execution_plan_hash
    assert engine.storage.get('project') == engine.storage._deserialize(failed.plan.after_state)
    event, = engine.events.list_for_target('project')
    assert event.event_id == 'event' and event.revision == 1
    entry, = completed.manual_resolutions
    assert entry['action'] == 'RETRY_THREAD_CREATE_V1'
    assert entry['failed_record_sha256'] == report['failed_record_sha256']
    assert result['revision'] == 1 and check_readiness(tmp_path)['ready']
    engine.storage.delete('project', previous_revision=1, operation_id='later-delete')
    after = fingerprints(tmp_path)
    assert retry(tmp_path, report) == result
    assert fingerprints(tmp_path) == after and engine.storage.get('project') is None


@pytest.mark.parametrize('change', ['thread', 'event', 'event-before-thread', 'bytes', 'report',
                                   'snapshot', 'missing-link', 'corrupt-link', 'unknown'])
def test_conflicts_never_publish_authorization(tmp_path, monkeypatch, change):
    backend, engine = seed(tmp_path, monkeypatch)
    report = review(tmp_path); record = engine.operations.get('create')
    after = engine.storage._deserialize(record.plan.after_state)
    if change == 'thread':
        engine.storage.create(replace(after, title='Foreign'))
    elif change in {'event', 'event-before-thread'}:
        event = engine._event(record, None, after)
        engine.events.save(replace(event, provenance=replace(event.provenance, source='foreign')) if change == 'event' else event)
    elif change == 'bytes':
        path = engine.operations._path('create'); path.write_text(path.read_text()+'\n')
    elif change == 'report':
        report['information_id'] = 'another'
    elif change == 'snapshot':
        changed = replace(record, plan=replace(record.plan,
            after_state=engine.storage._serialize_checked(replace(after, revision=2))))
        engine.operations._write(replace(changed, execution_plan_hash=plan_hash(changed)), engine.operations._path('create'))
    elif change == 'missing-link':
        backend._path('one').unlink()
    elif change == 'corrupt-link':
        backend._path('one').write_text('corrupt')
    else:
        path = backend.history_root / 'operations/unknown-v1'; path.mkdir()
        (path / 'foreign.json').write_text('{}')
    before = business_files(tmp_path)
    with pytest.raises((OperationConflict, ThreadStorageError)):
        retry(tmp_path, report)
    assert business_files(tmp_path) == before
    assert engine.operations.get('create').manual_resolutions == []
    assert engine.operations.get('create').status is OperationStatus.FAILED


@pytest.mark.parametrize('collision', ['thread', 'event', 'other-family', 'committed-creation'])
def test_reserved_identities_and_other_families_block_retry(tmp_path, monkeypatch, collision):
    _, engine = seed(tmp_path, monkeypatch); report = review(tmp_path)
    if collision == 'other-family':
        seed_status(tmp_path, monkeypatch, identity='another', opid='foreign')
    else:
        record = engine.operations.get('create')
        if collision == 'event':
            after = replace(engine.storage._deserialize(record.plan.after_state), thread_id='another')
            record = replace(record, target_id='another', plan=replace(record.plan,
                after_state=engine.storage._serialize_checked(after)))
        else:
            record = replace(record, plan=replace(record.plan, event_id='another-event'))
        record = replace(record, operation_id='other')
        engine.operations.create(replace(record, execution_plan_hash=plan_hash(record)))
        if collision == 'committed-creation':
            record = engine.operations.get('other')
            engine.operations._write(replace(record, status=OperationStatus.COMMITTED), engine.operations._path('other'))
    before = business_files(tmp_path)
    with pytest.raises(OperationConflict):
        retry(tmp_path, report)
    assert business_files(tmp_path) == before


@pytest.mark.parametrize('boundary', ['before_authorization', 'after_authorization', 'after_commit'])
def test_process_exit_and_ordinary_recovery(tmp_path, monkeypatch, boundary):
    _, engine = seed(tmp_path, monkeypatch); report = review(tmp_path)
    script = '''
import os, sys, json
import core.operations.failed_resolution as m
m._checkpoint = lambda stage: os._exit(74) if stage == sys.argv[3] else None
m.retry_failed_thread(sys.argv[1], json.loads(sys.argv[2]), resolution_id='decision', actor='human',
                      reason='Effects reviewed', timestamp='2026-10-03T01:00:00+02:00')
'''
    process = subprocess.run([sys.executable, '-B', '-c', script, str(tmp_path), json.dumps(report), boundary])
    assert process.returncode == 74
    record = engine.operations.get('create')
    if boundary == 'before_authorization':
        assert record.status is OperationStatus.FAILED and not record.manual_resolutions
        assert recover_all(tmp_path)['passes'] == 0
    else:
        assert len(record.manual_resolutions) == 1
        assert recover_all(tmp_path)['readiness']['ready']
    assert retry(tmp_path, report)['revision'] == 1
    assert len(engine.operations.get('create').manual_resolutions) == 1


def test_pending_delete_remains_blocked_before_and_after_retry(tmp_path, monkeypatch):
    backend, engine = seed(tmp_path, monkeypatch)
    backend.delete_request('one', 'human', 'Later request', 1, 'delete-one')
    with pytest.raises(InformationDeletionBlocked):
        backend.approve_delete('one', 'delete-one')
    retry(tmp_path, review(tmp_path))
    with pytest.raises(InformationDeletionBlocked):
        backend.approve_delete('one', 'delete-one')
    assert backend.get('one') is not None and engine.storage.get('project') is not None


@pytest.mark.parametrize('change', ['action', 'actor', 'timestamp', 'duplicate'])
def test_corrupt_audit_blocks_readiness_and_recovery(tmp_path, monkeypatch, change):
    _, engine = seed(tmp_path, monkeypatch); retry(tmp_path, review(tmp_path))
    path = engine.operations._path('create'); data = json.loads(path.read_text())
    entry = data['manual_resolutions'][0]
    if change == 'duplicate':
        data['manual_resolutions'].append(dict(entry))
    else:
        entry[change] = {'action':'RETRY_THREAD_STATUS_V1', 'actor':'', 'timestamp':'2026-10-03'}[change]
    path.write_text(json.dumps(data)); before = fingerprints(tmp_path)
    assert not check_readiness(tmp_path)['ready'] and recover_all(tmp_path)['passes'] == 0
    assert fingerprints(tmp_path) == before


def test_status_api_generic_repository_and_cli(tmp_path, monkeypatch, capsys):
    missing = tmp_path/'missing'
    assert main(['--root', str(missing), 'preview', 'create', '--family', FAMILY]) == 1
    assert not missing.exists(); capsys.readouterr()
    _, engine = seed(tmp_path, monkeypatch)
    before = fingerprints(tmp_path)
    assert main(['--root', str(tmp_path), 'preview', 'create', '--family', FAMILY]) == 0
    report = json.loads(capsys.readouterr().out)
    assert fingerprints(tmp_path) == before
    with pytest.raises(ValueError):
        retry_failed_status(tmp_path, report, resolution_id='d', actor='h', reason='r', timestamp=STAMP)
    with pytest.raises(ValueError):
        engine.operations.update(replace(engine.operations.get('create'), status=OperationStatus.APPLYING))
    path=tmp_path/'review.json';path.write_text(json.dumps(report))
    assert main(['--root', str(tmp_path), 'retry', '--review', str(path), '--resolution-id', 'decision',
                 '--actor', 'human', '--reason', 'Effects reviewed', '--timestamp', STAMP]) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'COMMITTED'
    completed=engine.operations.get('create')
    with pytest.raises(OperationConflict):
        engine.operations.update(replace(completed, manual_resolutions=[]))


def test_two_processes_authorize_exactly_once(tmp_path, monkeypatch):
    _, engine = seed(tmp_path, monkeypatch); report = review(tmp_path)
    script = '''
import sys, json
from core.operations.failed_resolution import retry_failed_thread
print(json.dumps(retry_failed_thread(sys.argv[1], json.loads(sys.argv[2]), resolution_id='decision',
 actor='human', reason='Effects reviewed', timestamp='2026-10-03T01:00:00+02:00')))
'''
    commands = [sys.executable, '-B', '-c', script, str(tmp_path), json.dumps(report)]
    processes = [subprocess.Popen(commands, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                 for _ in range(2)]
    results = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=20)
        assert process.returncode == 0, stderr
        results.append(json.loads(stdout))
    assert results[0] == results[1]
    assert len(engine.operations.get('create').manual_resolutions) == 1
    assert len(engine.events.list_for_target('project')) == 1


@pytest.mark.parametrize('field,value', [('actor',''), ('reason',' '), ('timestamp','2026-10-03'),
                                         ('resolution_id','bad/id')])
def test_invalid_decision_does_not_write(tmp_path, monkeypatch, field, value):
    seed(tmp_path, monkeypatch); report = review(tmp_path); before = fingerprints(tmp_path)
    with pytest.raises((ValueError, InvalidOperationRecord)):
        retry(tmp_path, report, **{field:value})
    assert fingerprints(tmp_path) == before


def test_second_failure_requires_new_decision(tmp_path, monkeypatch):
    _, engine = seed(tmp_path, monkeypatch); report = review(tmp_path)
    import core.operations.failed_resolution as module
    def stop(stage):
        if stage == 'after_authorization':
            raise RuntimeError('stopped')
    with monkeypatch.context() as patch:
        patch.setattr(module, '_checkpoint', stop)
        with pytest.raises(RuntimeError):
            retry(tmp_path, report)
    engine.operations.update(replace(engine.operations.get('create'), status=OperationStatus.FAILED))
    before = business_files(tmp_path)
    with pytest.raises(OperationConflict):
        retry(tmp_path, report)
    assert business_files(tmp_path) == before
    retry(tmp_path, review(tmp_path), resolution_id='second', reason='Cause reviewed again')
    assert len(engine.operations.get('create').manual_resolutions) == 2


def test_independent_failed_creations_resolve_one_at_a_time(tmp_path, monkeypatch):
    _, engine = seed(tmp_path, monkeypatch)
    seed(tmp_path, monkeypatch, identity='another', opid='other', eventid='other-event')
    retry(tmp_path, review(tmp_path))
    assert not check_readiness(tmp_path)['ready']
    other = review_failed_thread(tmp_path, 'other', family=FAMILY)
    retry(tmp_path, other, resolution_id='other-decision')
    assert check_readiness(tmp_path)['ready']
    assert engine.storage.get('another') is not None
