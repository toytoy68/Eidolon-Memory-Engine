"""Frozen Information commands survive manual retry and audit-preserving compaction."""
from dataclasses import replace
import json
import subprocess
import sys

import pytest

from core.backend.errors import RevisionConflict
from core.information.failed_resolution import review_failed_information, retry_failed_information, main
from core.information.writes import expected_event, validate_operation
from core.operations.errors import OperationConflict, InvalidOperationRecord
from core.operations.models import OperationStatus
from core.operations.readiness import check_readiness, recover_all
from core.operations.thread_status import plan_hash
from tests.test_information_writes import service, memory, command
from tests.test_failed_status_resolution import business_files, seed as seed_status
from tests.test_migration_converter import fingerprints

STAMP = '2026-10-03T01:00:00+02:00'


def seed(root, monkeypatch, kind='create', phase='before'):
    writer = service(root)
    target = memory()
    if kind == 'update':
        writer.create(target, **command('initial'))
        target = replace(target, content='Updated private content')
    def stop(*args, **kw):
        raise RuntimeError('stopped')
    with monkeypatch.context() as patch:
        if phase == 'before':
            patch.setattr(writer, '_resume', stop)
        elif phase == 'memory':
            patch.setattr(writer.events, 'save', stop)
        else:
            original = writer.operations.update
            def before_commit(record):
                if record.status is OperationStatus.COMMITTED:
                    stop()
                original(record)
            patch.setattr(writer.operations, 'update', before_commit)
        with pytest.raises(RuntimeError):
            if kind == 'create':
                writer.create(target, **command('failed'))
            else:
                writer.update(target, previous_revision=1, **command('failed'))
    writer.operations.update(replace(writer.operations.get('failed'), status=OperationStatus.FAILED))
    return writer


def review(root):
    return review_failed_information(root, 'failed')


def retry(root, report, **kw):
    decision = dict(resolution_id='decision', actor='human', reason='Effects reviewed', timestamp=STAMP)
    decision.update(kw)
    return retry_failed_information(root, report, **decision)


@pytest.mark.parametrize('kind', ['create', 'update'])
@pytest.mark.parametrize('phase', ['before', 'memory', 'event'])
def test_original_write_retries_once_without_promoting_metadata(tmp_path, monkeypatch, kind, phase):
    writer = seed(tmp_path, monkeypatch, kind, phase)
    failed = writer.operations.get('failed'); before = fingerprints(tmp_path)
    report = review(tmp_path)
    assert fingerprints(tmp_path) == before
    assert report['action'] == 'RETRY_INFORMATION_WRITE_V1'
    assert report['operation_type'] == 'INFORMATION_' + kind.upper()
    assert report['information_state'] == (('ABSENT' if kind == 'create' else 'BEFORE') if phase == 'before' else 'AFTER')
    assert report['event_state'] == ('MATCH' if phase == 'event' else 'ABSENT')
    assert report['write_information'] == (phase == 'before')
    assert not check_readiness(tmp_path)['ready'] and recover_all(tmp_path)['passes'] == 0
    result = retry(tmp_path, report)
    completed = writer.operations.get('failed')
    assert completed.plan == failed.plan and plan_hash(completed) == failed.execution_plan_hash
    assert completed.status is OperationStatus.COMMITTED
    after = writer.backend._deserialize(failed.plan.after_state)
    assert writer.backend.get('info-1') == after
    assert after.metadata['epistemic_status'] == 'CONFLICTED'
    assert writer.events.get('event-failed') == expected_event(failed, writer.backend)
    entry, = completed.manual_resolutions
    assert entry['action'] == 'RETRY_INFORMATION_WRITE_V1'
    assert entry['failed_record_sha256'] == report['failed_record_sha256']
    assert result['result']['revision'] == (1 if kind == 'create' else 2)
    assert check_readiness(tmp_path)['ready']
    before = fingerprints(tmp_path)
    assert retry(tmp_path, report) == result and fingerprints(tmp_path) == before


@pytest.mark.parametrize('kind', ['create', 'update'])
@pytest.mark.parametrize('change', ['memory', 'event', 'event-before-memory', 'bytes', 'report',
                                   'snapshot', 'receipt', 'unknown', 'deletion'])
def test_conflicts_never_authorize_or_overwrite(tmp_path, monkeypatch, kind, change):
    writer = seed(tmp_path, monkeypatch, kind); report = review(tmp_path)
    failed = writer.operations.get('failed')
    _, after = validate_operation(failed, writer.backend)
    if change == 'memory':
        writer.backend._atomic_write(writer.backend._path('info-1'),
            writer.backend._serialize_checked(replace(after, content='Foreign')))
    elif change in {'event', 'event-before-memory'}:
        event = expected_event(failed, writer.backend)
        writer.events.save(replace(event, provenance=replace(event.provenance, source='foreign')) if change == 'event' else event)
    elif change == 'bytes':
        path = writer.operations._path('failed'); path.write_text(path.read_text()+'\n')
    elif change == 'report':
        report['revision'] = 999
    elif change == 'snapshot':
        changed = replace(failed, plan=replace(failed.plan,
            after_state=writer.backend._serialize_checked(replace(after, content='Forged'))))
        writer.operations._write(replace(changed, execution_plan_hash=plan_hash(changed)),writer.operations._path('failed'))
    elif change == 'receipt':
        path = writer.journal.receipt_path('failed'); path.parent.mkdir(parents=True)
        path.write_text('{}')
    elif change == 'deletion':
        # A conflicting receipt copied from a different stopped tree is never approved.
        other = service(tmp_path/'foreign')
        other.backend.store(memory())
        other.backend.delete_request('info-1','human','Remove',1,'delete')
        receipt = other.backend.pending_delete_root/'info-1.json'
        destination = writer.backend.pending_delete_root/'info-1.json'
        destination.parent.mkdir(parents=True,exist_ok=True); destination.write_bytes(receipt.read_bytes())
    else:
        folder = writer.backend.history_root/'operations/unknown-v1'; folder.mkdir()
        (folder/'foreign.json').write_text('{}')
    before = business_files(tmp_path)
    with pytest.raises((OperationConflict, InvalidOperationRecord)):
        retry(tmp_path, report)
    assert business_files(tmp_path) == before
    assert writer.operations.get('failed').manual_resolutions == []


@pytest.mark.parametrize('kind', ['create', 'update'])
@pytest.mark.parametrize('boundary', ['before_authorization', 'after_authorization', 'after_commit'])
def test_real_process_exit_and_ordinary_recovery(tmp_path, monkeypatch, kind, boundary):
    writer = seed(tmp_path, monkeypatch, kind); report = review(tmp_path)
    script = '''
import os, sys, json
import core.information.failed_resolution as m
m._checkpoint=lambda stage: os._exit(74) if stage==sys.argv[3] else None
m.retry_failed_information(sys.argv[1],json.loads(sys.argv[2]),resolution_id='decision',actor='human',
 reason='Effects reviewed',timestamp='2026-10-03T01:00:00+02:00')
'''
    process = subprocess.run([sys.executable,'-B','-c',script,str(tmp_path),json.dumps(report),boundary])
    assert process.returncode == 74
    record = writer.operations.get('failed')
    if boundary == 'before_authorization':
        assert record.status is OperationStatus.FAILED and not record.manual_resolutions
        assert recover_all(tmp_path)['passes'] == 0
    else:
        assert record.status is (OperationStatus.APPLYING if boundary == 'after_authorization' else OperationStatus.COMMITTED)
        assert len(record.manual_resolutions) == 1
        assert recover_all(tmp_path)['readiness']['ready']
    assert retry(tmp_path,report)['result']['revision'] == (1 if kind == 'create' else 2)


@pytest.mark.parametrize('kind', ['create', 'update'])
def test_audit_survives_compaction_and_replay_after_deletion(tmp_path,monkeypatch,kind):
    writer = seed(tmp_path,monkeypatch,kind); report=review(tmp_path); result=retry(tmp_path,report)
    before_audit=writer.operations.get('failed').manual_resolutions
    for opid in writer.journal.ids():
        writer.compact(opid)
    entry=writer.journal.read('failed')
    assert entry.operation is None and entry.receipt['manual_resolutions']==before_audit
    assert memory().content not in json.dumps(entry.receipt)
    revision=result['result']['revision']
    writer.backend.delete_request('info-1','human','Remove',revision,'delete-one')
    writer.backend.approve_delete('info-1','delete-one')
    assert writer.backend.get('info-1') is None
    before=fingerprints(tmp_path)
    assert retry(tmp_path,report)==result and fingerprints(tmp_path)==before
    with pytest.raises(OperationConflict):
        retry(tmp_path,report,resolution_id='another')
    with pytest.raises(OperationConflict):
        retry(tmp_path,report,reason='Changed decision')
    assert writer.backend.get('info-1') is None


@pytest.mark.parametrize('change',['action','timestamp','duplicate','missing-entry','empty'])
def test_bad_compact_audit_blocks_readiness_and_replay(tmp_path,monkeypatch,change):
    writer=seed(tmp_path,monkeypatch);report=review(tmp_path);retry(tmp_path,report);writer.compact('failed')
    path=writer.journal.receipt_path('failed');data=json.loads(path.read_text())
    entry=data['manual_resolutions'][0]
    if change=='duplicate':
        data['manual_resolutions'].append(dict(entry))
    elif change=='missing-entry':
        del entry['actor']
    elif change=='empty':
        data['manual_resolutions']=[]
    else:
        entry[change]={'action':'RETRY_THREAD_CREATE_V1','timestamp':'2026-10-03'}[change]
    path.write_text(json.dumps(data));before=fingerprints(tmp_path)
    if change != 'empty':
        assert not check_readiness(tmp_path)['ready'] and recover_all(tmp_path)['passes']==0
    with pytest.raises((OperationConflict,InvalidOperationRecord)):
        retry(tmp_path,report)
    assert business_files(tmp_path)=={k:v for k,v in before.items() if not k.endswith('.write.lock')}


@pytest.mark.parametrize('field,value',[('actor',''),('reason',' '),('timestamp','2026-10-03'),('resolution_id','bad/id')])
def test_invalid_decision_does_not_write(tmp_path,monkeypatch,field,value):
    seed(tmp_path,monkeypatch);report=review(tmp_path);before=fingerprints(tmp_path)
    with pytest.raises((ValueError,InvalidOperationRecord)):
        retry(tmp_path,report,**{field:value})
    assert fingerprints(tmp_path)==before


@pytest.mark.parametrize('collision',['target','event','thread-family'])
def test_reservations_block_authorization(tmp_path,monkeypatch,collision):
    writer=seed(tmp_path,monkeypatch);report=review(tmp_path)
    if collision=='thread-family':
        seed_status(tmp_path,monkeypatch,identity='another',opid='other')
    else:
        record=writer.operations.get('failed')
        if collision=='target':
            record=replace(record,operation_id='other')
        else:
            after=writer.backend._deserialize(record.plan.after_state)
            from core.information.writes import fingerprint
            after=replace(after,information_id='another')
            plan=replace(record.plan,after_state=writer.backend._serialize_checked(after),
                command_fingerprint=fingerprint(record.operation_type,after,0,record.plan.event_id,record.plan.actor,record.plan.timestamp))
            record=replace(record,operation_id='other',target_id='another',plan=plan)
        writer.operations.create(replace(record,execution_plan_hash=plan_hash(record)))
    before=business_files(tmp_path)
    with pytest.raises(OperationConflict):
        retry(tmp_path,report)
    assert business_files(tmp_path)==before


@pytest.mark.parametrize('kind',['create','update'])
def test_two_processes_authorize_once(tmp_path,monkeypatch,kind):
    writer=seed(tmp_path,monkeypatch,kind);report=review(tmp_path)
    script='''
import sys,json
from core.information.failed_resolution import retry_failed_information
print(json.dumps(retry_failed_information(sys.argv[1],json.loads(sys.argv[2]),resolution_id='decision',
 actor='human',reason='Effects reviewed',timestamp='2026-10-03T01:00:00+02:00')))
'''
    command_line=[sys.executable,'-B','-c',script,str(tmp_path),json.dumps(report)]
    processes=[subprocess.Popen(command_line,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)]
    results=[]
    for process in processes:
        stdout,stderr=process.communicate(timeout=20)
        assert process.returncode==0,stderr
        results.append(json.loads(stdout))
    assert results[0]==results[1] and len(writer.operations.get('failed').manual_resolutions)==1
    assert writer.events.get('event-failed') is not None


def test_generic_repository_and_old_compact_receipts(tmp_path,monkeypatch):
    writer=seed(tmp_path,monkeypatch)
    with pytest.raises(ValueError):
        writer.operations.update(replace(writer.operations.get('failed'),status=OperationStatus.APPLYING))
    retry(tmp_path,review(tmp_path));op=writer.operations.get('failed')
    with pytest.raises(OperationConflict):
        writer.operations.update(replace(op,manual_resolutions=[]))
    writer.create(replace(memory(),information_id='another'),**command('ordinary'))
    writer.compact('ordinary')
    assert 'manual_resolutions' not in writer.journal.read('ordinary').receipt


def test_second_failure_requires_new_decision(tmp_path,monkeypatch):
    writer=seed(tmp_path,monkeypatch);report=review(tmp_path)
    import core.information.failed_resolution as module
    def stop(stage):
        if stage=='after_authorization':
            raise RuntimeError('stopped')
    with monkeypatch.context() as patch:
        patch.setattr(module,'_checkpoint',stop)
        with pytest.raises(RuntimeError):
            retry(tmp_path,report)
    writer.operations.update(replace(writer.operations.get('failed'),status=OperationStatus.FAILED))
    with pytest.raises(OperationConflict):
        retry(tmp_path,report)
    retry(tmp_path,review(tmp_path),resolution_id='second')
    assert len(writer.operations.get('failed').manual_resolutions)==2
    writer.compact('failed')
    assert len(writer.journal.read('failed').receipt['manual_resolutions'])==2


def test_cli_and_missing_root_preview_are_read_only(tmp_path,monkeypatch,capsys):
    missing=tmp_path/'missing'
    assert main(['--root',str(missing),'preview','failed'])==1
    assert not missing.exists();capsys.readouterr()
    seed(tmp_path,monkeypatch);before=fingerprints(tmp_path)
    assert main(['--root',str(tmp_path),'preview','failed'])==0
    report=capsys.readouterr().out;assert fingerprints(tmp_path)==before
    path=tmp_path/'review.json';path.write_text(report)
    assert main(['--root',str(tmp_path),'retry','--review',str(path),'--resolution-id','decision',
                 '--actor','human','--reason','Effects reviewed','--timestamp',STAMP])==0
    assert json.loads(capsys.readouterr().out)['status']=='COMMITTED'


def test_independent_failed_writes_resolve_one_at_a_time(tmp_path,monkeypatch):
    writer=seed(tmp_path,monkeypatch)
    def stop(*args,**kw):
        raise RuntimeError('stopped')
    with monkeypatch.context() as patch:
        patch.setattr(writer,'_resume',stop)
        with pytest.raises(RuntimeError):
            writer.create(replace(memory(),information_id='another'),**command('other'))
    writer.operations.update(replace(writer.operations.get('other'),status=OperationStatus.FAILED))
    retry(tmp_path,review(tmp_path));assert not check_readiness(tmp_path)['ready']
    other=review_failed_information(tmp_path,'other')
    retry(tmp_path,other,resolution_id='other-decision')
    assert check_readiness(tmp_path)['ready']


@pytest.mark.parametrize('change',['action','timestamp','duplicate','missing-entry'])
def test_bad_full_journal_audit_blocks_readiness(tmp_path,monkeypatch,change):
    writer=seed(tmp_path,monkeypatch);retry(tmp_path,review(tmp_path))
    path=writer.operations._path('failed');data=json.loads(path.read_text())
    entry=data['manual_resolutions'][0]
    if change=='duplicate':
        data['manual_resolutions'].append(dict(entry))
    elif change=='missing-entry':
        del entry['actor']
    else:
        entry[change]={'action':'RETRY_THREAD_CREATE_V1','timestamp':'2026-10-03'}[change]
    path.write_text(json.dumps(data));before=fingerprints(tmp_path)
    assert not check_readiness(tmp_path)['ready'] and recover_all(tmp_path)['passes']==0
    assert fingerprints(tmp_path)==before


def test_compaction_interrupt_preserves_trace_in_both_records(tmp_path,monkeypatch):
    writer=seed(tmp_path,monkeypatch);report=review(tmp_path);result=retry(tmp_path,report)
    import core.information.compaction as module
    def stop(path):
        raise RuntimeError('stopped before unlink')
    with monkeypatch.context() as patch:
        patch.setattr(module,'durable_unlink',stop)
        with pytest.raises(RuntimeError):
            writer.compact('failed')
    entry=writer.journal.read('failed')
    assert entry.receipt['manual_resolutions']==entry.operation.manual_resolutions
    assert retry(tmp_path,report)==result
    assert recover_all(tmp_path)['readiness']['ready']
    assert writer.journal.read('failed').operation is None


def test_divergent_compaction_audit_never_retires_snapshot(tmp_path,monkeypatch):
    writer=seed(tmp_path,monkeypatch);retry(tmp_path,review(tmp_path))
    import core.information.compaction as module
    def stop(path):
        raise RuntimeError('stopped')
    with monkeypatch.context() as patch:
        patch.setattr(module,'durable_unlink',stop)
        with pytest.raises(RuntimeError):
            writer.compact('failed')
    path=writer.journal.receipt_path('failed');data=json.loads(path.read_text())
    data['manual_resolutions'][0]['reason']='Different valid audit'
    path.write_text(json.dumps(data));before=fingerprints(tmp_path)
    with pytest.raises(OperationConflict):
        writer.compact('failed')
    assert not check_readiness(tmp_path)['ready'] and writer.operations._path('failed').exists()
    assert fingerprints(tmp_path)==before


def test_cancelled_deletion_allows_original_update_only(tmp_path,monkeypatch):
    writer=service(tmp_path);writer.backend.store(memory())
    writer.backend.delete_request('info-1','human','Remove',1,'delete-one')
    writer.backend.cancel_delete('info-1','delete-one')
    def stop(*args,**kw):
        raise RuntimeError('stopped')
    with monkeypatch.context() as patch:
        patch.setattr(writer,'_resume',stop)
        with pytest.raises(RuntimeError):
            writer.update(replace(memory(),content='Reviewed update'),previous_revision=1,**command('failed'))
    writer.operations.update(replace(writer.operations.get('failed'),status=OperationStatus.FAILED))
    retry(tmp_path,review(tmp_path))
    assert writer.backend.get('info-1').content=='Reviewed update'
    assert writer._deletion_status('info-1')=='CANCELLED'


def test_deleted_relation_target_blocks_before_authorization(tmp_path,monkeypatch):
    writer=service(tmp_path)
    target=replace(memory(),information_id='target');writer.backend.store(target)
    original=replace(memory(),relations=[{'type':'RELATED_TO','target_id':'target'}])
    def stop(*args,**kw):
        raise RuntimeError('stopped')
    with monkeypatch.context() as patch:
        patch.setattr(writer,'_resume',stop)
        with pytest.raises(RuntimeError):
            writer.create(original,**command('failed'))
    writer.operations.update(replace(writer.operations.get('failed'),status=OperationStatus.FAILED))
    # Copy a terminal deletion reservation from another stopped tree.
    other=service(tmp_path/'foreign');other.backend.store(target)
    other.backend.delete_request('target','human','Remove',1,'delete-target')
    other.backend.approve_delete('target','delete-target')
    receipt=other.backend.pending_delete_root/'target.json'
    destination=writer.backend.pending_delete_root/'target.json'
    destination.write_bytes(receipt.read_bytes());writer.backend._path('target').unlink()
    before=business_files(tmp_path)
    with pytest.raises(RevisionConflict):
        review(tmp_path)
    assert business_files(tmp_path)==before
