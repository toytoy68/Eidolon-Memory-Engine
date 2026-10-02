"""Human retry of a failed deletion never removes a divergent replacement."""
from dataclasses import replace
import json
import subprocess
import sys

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.operations.errors import OperationConflict, InvalidOperationRecord
from core.operations.failed_resolution import review_failed_thread, retry_failed_thread, retry_failed_status, main
from core.operations.models import OperationStatus
from core.operations.readiness import check_readiness, recover_all
from core.operations.thread_delete import FilesystemThreadDeletion
from core.operations.thread_status import plan_hash
from core.threads.models import Thread
from core.threads.storage import ThreadStorage, ThreadStorageError
from tests.test_failed_status_resolution import business_files, seed as seed_status
from tests.test_migration_converter import fingerprints

FAMILY = 'thread-delete-v1'
STAMP = '2026-10-03T01:00:00+02:00'


def seed(root, monkeypatch, phase='before', identity='project', opid='delete'):
    backend = FilesystemBackend(root / 'memory/persistent', root / 'memory/history')
    if backend.get('one') is None:
        backend.store(Memory('one', content='Source'))
    storage = ThreadStorage(backend.persistent_root)
    storage.create(Thread(identity, 'Project', 'Goal', created_at=STAMP, updated_at=STAMP,
                          relations=[{'type':'CONCERNS', 'target_id':'one'}]))
    engine = FilesystemThreadDeletion.for_history(storage, backend.history_root)
    def stop(*args, **kw):
        raise RuntimeError('stopped')
    with monkeypatch.context() as patch:
        if phase == 'before':
            patch.setattr(engine, '_resume', stop)
        elif phase == 'applying':
            patch.setattr(storage, '_delete_committed', stop)
        else:
            update = engine.operations.update
            def before_commit(record):
                if record.status is OperationStatus.COMMITTED:
                    stop()
                update(record)
            patch.setattr(engine.operations, 'update', before_commit)
        with pytest.raises(RuntimeError):
            engine.delete(identity, previous_revision=1, operation_id=opid)
    engine.operations.update(replace(engine.operations.get(opid), status=OperationStatus.FAILED))
    return backend, engine


def review(root):
    return review_failed_thread(root, 'delete', family=FAMILY)


def retry(root, report, **kw):
    decision = dict(resolution_id='decision', actor='human', reason='Deletion reviewed', timestamp=STAMP)
    decision.update(kw)
    return retry_failed_thread(root, report, **decision)


@pytest.mark.parametrize('phase', ['before', 'applying', 'absent'])
def test_delete_review_retry_preserves_plan_and_replays(tmp_path, monkeypatch, phase):
    _, engine = seed(tmp_path, monkeypatch, phase)
    failed = engine.operations.get('delete'); before = fingerprints(tmp_path)
    report = review(tmp_path)
    assert fingerprints(tmp_path) == before
    assert report['action'] == 'RETRY_THREAD_DELETE_V1'
    assert report['thread_state'] == ('ABSENT' if phase == 'absent' else 'BEFORE')
    assert report['delete_thread'] == (phase != 'absent')
    assert report['write_thread'] is False and report['write_event'] is False
    assert report['event_state'] == 'NOT_APPLICABLE'
    assert recover_all(tmp_path)['passes'] == 0
    result = retry(tmp_path, report)
    assert result == dict(status='COMMITTED', resolution_id='decision', operation_id='delete',
                         thread_id='project', revision=2)
    completed = engine.operations.get('delete')
    assert completed.status is OperationStatus.COMMITTED
    assert completed.plan == failed.plan and plan_hash(completed) == failed.execution_plan_hash
    entry, = completed.manual_resolutions
    assert entry['action'] == 'RETRY_THREAD_DELETE_V1'
    assert entry['failed_record_sha256'] == report['failed_record_sha256']
    assert engine.storage.get('project') is None and check_readiness(tmp_path)['ready']
    assert not (tmp_path/'memory/history/events/thread-delete-v1').exists()
    before = fingerprints(tmp_path)
    assert retry(tmp_path, report) == result and fingerprints(tmp_path) == before


@pytest.mark.parametrize('change', ['thread', 'replacement', 'bytes', 'report', 'snapshot', 'unknown',
                                   'symlink'])
def test_divergences_never_authorize_or_remove_replacement(tmp_path, monkeypatch, change):
    _, engine = seed(tmp_path, monkeypatch, phase='absent' if change == 'replacement' else 'before')
    report = review(tmp_path); record = engine.operations.get('delete')
    before_thread = engine.storage._deserialize(record.plan.before_state)
    if change == 'thread':
        engine.storage._path('project').write_text(engine.storage._serialize_checked(replace(before_thread, title='Foreign')))
    elif change == 'replacement':
        engine.storage.create(replace(before_thread, title='Replacement'))
    elif change == 'bytes':
        path=engine.operations._path('delete');path.write_text(path.read_text()+'\n')
    elif change == 'report':
        report['delete_thread'] = False
    elif change == 'snapshot':
        changed=replace(record, plan=replace(record.plan,
            before_state=engine.storage._serialize_checked(replace(before_thread, revision=2))))
        engine.operations._write(replace(changed, execution_plan_hash=plan_hash(changed)), engine.operations._path('delete'))
    elif change == 'unknown':
        folder=tmp_path/'memory/history/operations/unknown-v1';folder.mkdir()
        (folder/'foreign.json').write_text('{}')
    else:
        path=engine.storage._path('project');target=tmp_path/'foreign.md'
        target.write_bytes(path.read_bytes());path.unlink();path.symlink_to(target)
    before=business_files(tmp_path)
    with pytest.raises((OperationConflict, ThreadStorageError)):
        retry(tmp_path, report)
    assert business_files(tmp_path) == before
    failed=engine.operations.get('delete')
    assert failed.status is OperationStatus.FAILED and failed.manual_resolutions == []


@pytest.mark.parametrize('collision', ['thread', 'other-family', 'committed-operation-id'])
def test_dependencies_and_identity_collisions_block_before_authorization(tmp_path, monkeypatch, collision):
    _,engine=seed(tmp_path,monkeypatch);report=review(tmp_path)
    if collision == 'thread':
        record=engine.operations.get('delete')
        other=replace(record,operation_id='other')
        engine.operations.create(replace(other,execution_plan_hash=plan_hash(other)))
    else:
        other=seed_status(tmp_path,monkeypatch,identity='another',opid='delete' if collision=='committed-operation-id' else 'other')
        if collision == 'committed-operation-id':
            record=other.operations.get('delete')
            other.operations._write(replace(record,status=OperationStatus.COMMITTED),other.operations._path('delete'))
    before=business_files(tmp_path)
    with pytest.raises(OperationConflict):
        retry(tmp_path,report)
    assert business_files(tmp_path)==before


@pytest.mark.parametrize('boundary',['before_authorization','after_authorization','after_commit'])
def test_process_exit_and_ordinary_recovery(tmp_path,monkeypatch,boundary):
    _,engine=seed(tmp_path,monkeypatch);report=review(tmp_path)
    script='''
import os, sys, json
import core.operations.failed_resolution as m
m._checkpoint=lambda stage: os._exit(74) if stage==sys.argv[3] else None
m.retry_failed_thread(sys.argv[1],json.loads(sys.argv[2]),resolution_id='decision',actor='human',
 reason='Deletion reviewed',timestamp='2026-10-03T01:00:00+02:00')
'''
    process=subprocess.run([sys.executable,'-B','-c',script,str(tmp_path),json.dumps(report),boundary])
    assert process.returncode==74
    record=engine.operations.get('delete')
    if boundary=='before_authorization':
        assert record.status is OperationStatus.FAILED and not record.manual_resolutions
        assert recover_all(tmp_path)['passes']==0
    else:
        assert len(record.manual_resolutions)==1
        assert record.status is (OperationStatus.APPLYING if boundary=='after_authorization' else OperationStatus.COMMITTED)
        assert recover_all(tmp_path)['readiness']['ready']
    assert retry(tmp_path,report)['revision']==2
    assert engine.storage.get('project') is None


def test_retry_does_not_require_deleted_link_and_releases_live_reference(tmp_path,monkeypatch):
    backend,engine=seed(tmp_path,monkeypatch)
    backend.delete_request('one','human','Remove after Thread',1,'delete-one')
    report=review(tmp_path)
    result=retry(tmp_path,report)
    backend.approve_delete('one','delete-one')
    assert backend.get('one') is None
    before=fingerprints(tmp_path)
    assert retry(tmp_path,report)==result
    # Replay the original decision remains terminal, with no link recreation.
    assert engine.storage.get('project') is None
    assert fingerprints(tmp_path)==before


def test_absent_thread_can_finish_after_link_information_disappeared(tmp_path,monkeypatch):
    backend,engine=seed(tmp_path,monkeypatch,phase='absent')
    backend._path('one').unlink()
    retry(tmp_path,review(tmp_path))
    assert engine.operations.get('delete').status is OperationStatus.COMMITTED


@pytest.mark.parametrize('field,value',[('actor',''),('reason',' '),('timestamp','2026-10-03'),('resolution_id','bad/id')])
def test_invalid_decision_does_not_write(tmp_path,monkeypatch,field,value):
    seed(tmp_path,monkeypatch);report=review(tmp_path);before=fingerprints(tmp_path)
    with pytest.raises((ValueError,InvalidOperationRecord)):
        retry(tmp_path,report,**{field:value})
    assert fingerprints(tmp_path)==before


@pytest.mark.parametrize('change',['action','timestamp','duplicate'])
def test_corrupt_audit_blocks_readiness(tmp_path,monkeypatch,change):
    _,engine=seed(tmp_path,monkeypatch);retry(tmp_path,review(tmp_path))
    path=engine.operations._path('delete');data=json.loads(path.read_text())
    entry=data['manual_resolutions'][0]
    if change=='duplicate':
        data['manual_resolutions'].append(dict(entry))
    else:
        entry[change]={'action':'RETRY_THREAD_CREATE_V1','timestamp':'2026-10-03'}[change]
    path.write_text(json.dumps(data));before=fingerprints(tmp_path)
    assert not check_readiness(tmp_path)['ready'] and recover_all(tmp_path)['passes']==0
    assert fingerprints(tmp_path)==before


def test_terminal_replay_refuses_reused_identity(tmp_path,monkeypatch):
    _,engine=seed(tmp_path,monkeypatch);report=review(tmp_path);retry(tmp_path,report)
    original=engine.storage._deserialize(engine.operations.get('delete').plan.before_state)
    engine.storage.create(replace(original,title='Replacement'))
    before=business_files(tmp_path)
    with pytest.raises(OperationConflict):
        retry(tmp_path,report)
    assert business_files(tmp_path)==before and engine.storage.get('project').title=='Replacement'


def test_second_failure_requires_new_decision(tmp_path,monkeypatch):
    _,engine=seed(tmp_path,monkeypatch);report=review(tmp_path)
    import core.operations.failed_resolution as module
    def stop(stage):
        if stage=='after_authorization':
            raise RuntimeError('stopped')
    with monkeypatch.context() as patch:
        patch.setattr(module,'_checkpoint',stop)
        with pytest.raises(RuntimeError):
            retry(tmp_path,report)
    engine.operations.update(replace(engine.operations.get('delete'),status=OperationStatus.FAILED))
    with pytest.raises(OperationConflict):
        retry(tmp_path,report)
    retry(tmp_path,review(tmp_path),resolution_id='second')
    assert len(engine.operations.get('delete').manual_resolutions)==2


def test_two_processes_authorize_exactly_once(tmp_path,monkeypatch):
    _,engine=seed(tmp_path,monkeypatch);report=review(tmp_path)
    script='''
import sys,json
from core.operations.failed_resolution import retry_failed_thread
print(json.dumps(retry_failed_thread(sys.argv[1],json.loads(sys.argv[2]),resolution_id='decision',
 actor='human',reason='Deletion reviewed',timestamp='2026-10-03T01:00:00+02:00')))
'''
    commands=[sys.executable,'-B','-c',script,str(tmp_path),json.dumps(report)]
    processes=[subprocess.Popen(commands,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)]
    results=[]
    for process in processes:
        stdout,stderr=process.communicate(timeout=20)
        assert process.returncode==0,stderr
        results.append(json.loads(stdout))
    assert results[0]==results[1] and len(engine.operations.get('delete').manual_resolutions)==1
    assert engine.storage.get('project') is None


def test_independent_failed_deletions_resolve_one_at_a_time(tmp_path,monkeypatch):
    _,engine=seed(tmp_path,monkeypatch)
    seed(tmp_path,monkeypatch,identity='another',opid='other')
    retry(tmp_path,review(tmp_path));assert not check_readiness(tmp_path)['ready']
    other=review_failed_thread(tmp_path,'other',family=FAMILY)
    retry(tmp_path,other,resolution_id='other-decision')
    assert check_readiness(tmp_path)['ready'] and engine.storage.get('another') is None


def test_status_api_generic_repository_and_cli(tmp_path,monkeypatch,capsys):
    missing=tmp_path/'missing'
    assert main(['--root',str(missing),'preview','delete','--family',FAMILY])==1
    assert not missing.exists();capsys.readouterr()
    _,engine=seed(tmp_path,monkeypatch);before=fingerprints(tmp_path)
    assert main(['--root',str(tmp_path),'preview','delete','--family',FAMILY])==0
    report=json.loads(capsys.readouterr().out);assert fingerprints(tmp_path)==before
    with pytest.raises(ValueError):
        retry_failed_status(tmp_path,report,resolution_id='d',actor='h',reason='r',timestamp=STAMP)
    with pytest.raises(ValueError):
        engine.operations.update(replace(engine.operations.get('delete'),status=OperationStatus.APPLYING))
    path=tmp_path/'review.json';path.write_text(json.dumps(report))
    assert main(['--root',str(tmp_path),'retry','--review',str(path),'--resolution-id','decision',
                 '--actor','human','--reason','Deletion reviewed','--timestamp',STAMP])==0
    assert json.loads(capsys.readouterr().out)['status']=='COMMITTED'
    with pytest.raises(OperationConflict):
        engine.operations.update(replace(engine.operations.get('delete'),manual_resolutions=[]))
