"""A bounded compaction shares reservations without losing durable receipts."""
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.information.write_audit import audit_information_writes
from core.information.writes import FilesystemInformationWrites
from core.operations.models import OperationStatus
from tests.test_failed_information_resolution import seed as failed_seed, retry as failed_retry
from core.information.failed_resolution import review_failed_information
from tests.test_migration_converter import fingerprints
from tools.benchmark_information_writes import count_reads


def seed(root,count=4):
    writer=FilesystemInformationWrites(FilesystemBackend(root/'memory/persistent',root/'memory/history'))
    originals=[]
    for i in range(count):
        memory=Memory(f'info-{i}',content=f'Private text {i}')
        args=dict(operation_id=f'create-{i}',event_id=f'event-{i}',actor='human',timestamp='fixed')
        originals.append((memory,args,writer.create(memory,**args)))
    return writer,originals


def compacted(writer):
    return [identity for identity in writer.journal.ids() if writer.journal.read(identity).operation is None]


def test_batch_compacts_with_one_scan_and_preserves_exact_replay(tmp_path):
    writer,originals=seed(tmp_path,8);ids=[args['operation_id'] for _,args,_ in originals]
    before={str(p):p.read_bytes() for p in [*writer.backend.persistent_root.glob('*.md'),*writer.events.events_root.glob('*.md')]}
    with count_reads() as counts:result=writer.compact_batch(ids)
    assert result['status']=='COMPLETED' and result['next_index']==result['total']==8
    assert [entry['operation_id'] for entry in result['results']]==ids and result['error'] is None
    assert counts['journal_scans']==1
    for memory,args,expected in originals:
        assert writer.create(memory,**args)==expected
        receipt=writer.journal.receipt_path(args['operation_id']).read_text()
        assert memory.content not in receipt and not writer.operations._path(args['operation_id']).exists()
    assert all(path.read_bytes()==data for path,data in ((Path(p),data) for p,data in before.items()))
    assert not audit_information_writes(tmp_path)['issues']
    snapshot=fingerprints(tmp_path)
    with count_reads() as counts:again=writer.compact_batch(ids)
    assert again==result and counts['journal_scans']==0 and fingerprints(tmp_path)==snapshot


@pytest.mark.parametrize('ids',[[],['a']*101,['create-0','create-0'],['create-0','../bad'],['create-0',True],('create-0',),['']])
def test_malformed_batch_is_rejected_before_any_publication(tmp_path,ids):
    writer,_=seed(tmp_path);before=fingerprints(tmp_path)
    with pytest.raises((ValueError,TypeError)):writer.compact_batch(ids)
    assert fingerprints(tmp_path)==before


@pytest.mark.parametrize('change',['missing-event','different-event','noncommitted','unknown-receipt','pending-same-target','deleted'])
def test_blocked_compaction_reports_prefix_and_leaves_suffix(tmp_path,monkeypatch,change):
    writer,originals=seed(tmp_path)
    if change=='missing-event':writer.events._path('event-1').unlink()
    elif change=='different-event':
        path=writer.events._path('event-1');path.write_text(path.read_text().replace('info-1','foreign'))
    elif change=='noncommitted':
        path=writer.operations._path('create-1');data=json.loads(path.read_text())
        data['status']='FAILED';path.write_text(json.dumps(data))
    elif change=='unknown-receipt':
        writer.compact('create-3');path=writer.journal.receipt_path('create-3')
        data=json.loads(path.read_text());data['format_version']=999;path.write_text(json.dumps(data))
    elif change=='pending-same-target':
        with monkeypatch.context() as patch:
            patch.setattr(writer,'_resume',lambda *args: (_ for _ in ()).throw(RuntimeError('stop')))
            with pytest.raises(RuntimeError):writer.update(originals[1][0],previous_revision=1,
                operation_id='pending',event_id='pending-event',actor='human',timestamp='fixed')
    else:
        # Public deletion refuses retained snapshots; emulate a stopped conflicting receipt.
        writer.backend.delete_request('info-1','human','Review',1,'delete')
        path=writer.backend.pending_delete_root/'info-1.json';data=json.loads(path.read_text());data['status']='DELETED';path.write_text(json.dumps(data))
    report=writer.compact_batch(['create-0','create-1','create-2'])
    assert report['status']=='BLOCKED' and report['total']==3
    assert report['next_index']==(0 if change=='unknown-receipt' else 1)
    assert report['error']['operation_id']==('create-0' if change=='unknown-receipt' else 'create-1')
    assert writer.operations._path('create-2').exists() and writer.operations._path('create-1').exists()
    if change!='unknown-receipt':assert not writer.operations._path('create-0').exists()


def test_batch_preserves_manual_failed_audit_and_deleted_replay(tmp_path,monkeypatch):
    writer=failed_seed(tmp_path,monkeypatch);review=review_failed_information(tmp_path,'failed')
    expected=failed_retry(tmp_path,review)
    audit=writer.operations.get('failed').manual_resolutions
    assert writer.compact_batch(['failed'])['status']=='COMPLETED'
    receipt=json.loads(writer.journal.receipt_path('failed').read_text())
    assert receipt['manual_resolutions']==audit and audit
    writer.backend.delete_request('info-1','human','Remove',1,'delete');writer.backend.approve_delete('info-1','delete')
    before=fingerprints(tmp_path)
    assert failed_retry(tmp_path,review)==expected and fingerprints(tmp_path)==before


def test_batch_rereads_published_receipt_before_retiring_snapshot(tmp_path,monkeypatch):
    writer,_=seed(tmp_path)
    import core.information.compaction as module
    real=module.atomic_write_text
    def corrupt(path,text):
        data=json.loads(text)
        if data['operation_id']=='create-1':data['event_sha256']='f'*64
        real(path,json.dumps(data))
    monkeypatch.setattr(module,'atomic_write_text',corrupt)
    result=writer.compact_batch(['create-0','create-1','create-2'])
    assert result['status']=='BLOCKED' and result['next_index']==1
    assert not writer.operations._path('create-0').exists()
    assert writer.operations._path('create-1').exists() and writer.operations._path('create-2').exists()


@pytest.mark.parametrize('boundary',['after-receipt','after-unlink','after-second-unlink'])
def test_process_exit_resumes_same_ordered_batch(tmp_path,boundary):
    writer,originals=seed(tmp_path)
    script='''
import os,sys
from pathlib import Path
from core.backend.filesystem import FilesystemBackend
from core.information.writes import FilesystemInformationWrites
import core.information.compaction as m
root=Path(sys.argv[1]);boundary=sys.argv[2]
name='atomic_write_text' if boundary=='after-receipt' else 'durable_unlink'
real=getattr(m,name);count=0
def interrupted(*args,**kwargs):
 global count
 real(*args,**kwargs);count+=1
 if count==(2 if boundary=='after-second-unlink' else 1):os._exit(74)
setattr(m,name,interrupted)
w=FilesystemInformationWrites(FilesystemBackend(root/'memory/persistent',root/'memory/history'))
w.compact_batch(['create-0','create-1','create-2','create-3'])
'''
    process=subprocess.run([sys.executable,'-B','-c',script,str(tmp_path),boundary])
    assert process.returncode==74
    report=writer.compact_batch([f'create-{i}' for i in range(4)])
    assert report['status']=='COMPLETED' and len(compacted(writer))==4
    assert not audit_information_writes(tmp_path)['issues']
    for memory,args,expected in originals:assert writer.create(memory,**args)==expected


def test_two_processes_compact_same_batch_without_losing_receipts(tmp_path):
    writer,_=seed(tmp_path)
    script='''
import json,sys
from pathlib import Path
from core.backend.filesystem import FilesystemBackend
from core.information.writes import FilesystemInformationWrites
root=Path(sys.argv[1]);w=FilesystemInformationWrites(FilesystemBackend(root/'memory/persistent',root/'memory/history'))
print(json.dumps(w.compact_batch(['create-0','create-1','create-2','create-3'])))
'''
    command=[sys.executable,'-B','-c',script,str(tmp_path)]
    processes=[subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)]
    results=[]
    for process in processes:
        stdout,stderr=process.communicate(timeout=20);assert process.returncode==0,stderr
        results.append(json.loads(stdout))
    assert results[0]==results[1] and results[0]['status']=='COMPLETED'
    assert len(compacted(writer))==4 and not audit_information_writes(tmp_path)['issues']


def test_each_new_batch_refreshes_reservations(tmp_path,monkeypatch):
    writer,originals=seed(tmp_path)
    assert writer.compact_batch(['create-0'])['status']=='COMPLETED'
    with monkeypatch.context() as patch:
        patch.setattr(writer,'_resume',lambda *a: (_ for _ in ()).throw(RuntimeError('stop')))
        with pytest.raises(RuntimeError):writer.update(originals[1][0],previous_revision=1,
            operation_id='pending',event_id='pending-event',actor='human',timestamp='fixed')
    result=writer.compact_batch(['create-1'])
    assert result['status']=='BLOCKED' and writer.operations._path('create-1').exists()


def test_compaction_cli_batch_reports_nonzero_on_blocked_prefix(tmp_path):
    writer,_=seed(tmp_path);ids=tmp_path/'ids.json';ids.write_text(json.dumps(['create-0','missing','create-2']))
    process=subprocess.run([sys.executable,'-B','-m','core.information.cli','compact-batch','--input',str(ids)],
        env=dict(os.environ,MEMORY_ENGINE_ROOT=str(tmp_path)),capture_output=True,text=True)
    assert process.returncode==1,process.stderr
    result=json.loads(process.stdout)
    assert result['status']=='BLOCKED' and result['next_index']==1
    assert not writer.operations._path('create-0').exists() and writer.operations._path('create-2').exists()


@pytest.mark.parametrize('indexed',[False,True])
def test_bounded_compaction_retains_event_reservations_after_missing_event(tmp_path,indexed):
    from core.operations.errors import OperationConflict
    writer,_=seed(tmp_path)
    if indexed:writer.rebuild_reservation_index()
    with count_reads() as counts:report=writer.compact_batch(['create-0','create-1','create-2'])
    assert report['status']=='COMPLETED' and counts['journal_scans']==1
    writer.events._path('event-1').unlink()
    with pytest.raises(OperationConflict):writer.create(Memory('foreign',content='new'),
        operation_id='foreign',event_id='event-1',actor='human',timestamp='fixed')
    assert writer.backend.get('foreign') is None


def test_one_batch_compacts_create_and_update_then_allows_human_deletion(tmp_path):
    writer,originals=seed(tmp_path)
    memory,args,created=originals[0]
    updated=writer.update(replace(memory,content='Corrected'),previous_revision=1,
        operation_id='update',event_id='updated',actor='human',timestamp='fixed')
    writer.backend.delete_request('info-0','human','Obsolete',2,'delete')
    report=writer.compact_batch(['create-0','update'])
    assert report['status']=='COMPLETED'
    writer.backend.approve_delete('info-0','delete')
    snapshot=fingerprints(tmp_path)
    assert writer.create(memory,**args)==created
    assert writer.update(replace(memory,content='Corrected'),previous_revision=1,
        operation_id='update',event_id='updated',actor='human',timestamp='fixed')==updated
    assert writer.backend.get('info-0') is None and fingerprints(tmp_path)==snapshot


def test_caller_cannot_reorder_a_running_batch(tmp_path,monkeypatch):
    writer,_=seed(tmp_path)
    identities=['create-0','create-1','create-2']
    import core.information.compaction as module
    real=module.atomic_write_text
    def changed(*args,**kwargs):
        identities[:]=['create-3']
        return real(*args,**kwargs)
    monkeypatch.setattr(module,'atomic_write_text',changed)
    report=writer.compact_batch(identities)
    assert report['status']=='COMPLETED'
    assert [item['operation_id'] for item in report['results']]==['create-0','create-1','create-2']
    assert writer.operations._path('create-3').exists()
