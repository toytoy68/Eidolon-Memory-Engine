"""Opt-in import retains cancellation history without activating a deletion."""
from dataclasses import replace
import json
import subprocess
import sys

import pytest

from core.backend.errors import BackendError, RevisionConflict
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.information.writes import FilesystemInformationWrites
from core.migration.deleted_receipts import inspect_deleted_receipts, import_deleted_receipts, main
from core.operations.errors import OperationConflict
from core.operations.readiness import check_readiness
from core.threads.models import Thread
from core.threads.storage import ThreadStorage
from tests.test_migration_converter import fingerprints

STAMP='2026-10-03T01:00:00+02:00'


def seed(root,count=2,updated=False):
    source,destination=root/'source',root/'destination'
    src=FilesystemBackend(source/'memory/persistent',source/'memory/history')
    dst=FilesystemBackend(destination/'memory/persistent',destination/'memory/history')
    for n in range(count):
        identity=f'cancelled-{n}'
        target=Memory(identity,content='Current body')
        src.store(target)
        src.delete_request(identity,'human','Reconsidered',1,f'delete-{n}')
        src.cancel_delete(identity,f'delete-{n}')
        if updated:
            writer=FilesystemInformationWrites(src)
            writer.update(replace(target,content='Later body'),previous_revision=1,
                          operation_id=f'update-{n}',event_id=f'event-{n}',actor='human',timestamp=STAMP)
            writer.compact(f'update-{n}')
        dst.store(src.get(identity))
    return source,destination,src,dst


@pytest.mark.parametrize('updated',[False,True])
def test_opt_in_preserves_cancellation_and_allows_update(tmp_path,updated):
    source,destination,src,dst=seed(tmp_path,updated=updated)
    before=fingerprints(tmp_path)
    assert inspect_deleted_receipts(source,destination)['status']=='BLOCKED'
    report=inspect_deleted_receipts(source,destination,include_cancelled=True)
    assert report['status']=='READY'
    assert {row['status'] for row in report['receipts']}=={'CANCELLED'}
    assert fingerprints(tmp_path)==before
    source_before=fingerprints(source)
    result=import_deleted_receipts(source,destination,include_cancelled=True)
    assert result['status']=='IMPORTED' and len(result['imported'])==2
    assert fingerprints(source)==source_before
    assert check_readiness(destination)['ready']
    for identity in ['cancelled-0','cancelled-1']:
        path=dst.pending_delete_root/(identity+'.json')
        assert path.read_bytes()==(src.pending_delete_root/path.name).read_bytes()
        current=dst.get(identity)
        with pytest.raises(RevisionConflict):
            dst.approve_delete(identity,'delete-'+identity[-1])
        writer=FilesystemInformationWrites(dst)
        with pytest.raises(OperationConflict):
            writer.create(Memory(identity),operation_id='create-'+identity,event_id='create-event-'+identity,
                          actor='human',timestamp=STAMP)
        assert writer.update(replace(current,content='Allowed edit'),previous_revision=current.revision,
                             operation_id='edit-'+identity,event_id='edit-event-'+identity,actor='human',timestamp=STAMP)['revision']==current.revision+1
    # Canonical divergence after a new edit prevents importing the old source again.
    assert import_deleted_receipts(source,destination,include_cancelled=True)['status']=='BLOCKED'


def test_unchanged_replay_does_not_rewrite(tmp_path):
    source,destination,_,_=seed(tmp_path)
    assert import_deleted_receipts(source,destination,include_cancelled=True)['status']=='IMPORTED'
    before=fingerprints(tmp_path)
    assert import_deleted_receipts(source,destination,include_cancelled=True)['status']=='UNCHANGED'
    assert fingerprints(tmp_path)==before


def test_mixed_deleted_cancelled_batch_is_supported_only_explicitly(tmp_path):
    source,destination,src,dst=seed(tmp_path)
    src.store(Memory('removed'))
    src.delete_request('removed','human','Remove',1,'remove')
    src.approve_delete('removed','remove')
    assert import_deleted_receipts(source,destination)['status']=='BLOCKED'
    result=import_deleted_receipts(source,destination,include_cancelled=True)
    assert result['status']=='IMPORTED'
    assert {row['status'] for row in result['receipts']}=={'DELETED','CANCELLED'}
    assert dst.get('removed') is None
    with pytest.raises(BackendError):
        dst.store(Memory('removed'))


@pytest.mark.parametrize('change',['different-body','missing-source','missing-destination','lower-revision',
                                   'different-receipt','symlink','corrupt-body','pending','applying','unknown'])
def test_all_conflicts_are_found_before_first_publication(tmp_path,change):
    source,destination,src,dst=seed(tmp_path)
    if change=='different-body':
        dst._path('cancelled-1').write_text(dst._serialize_checked(replace(dst.get('cancelled-1'),content='Foreign')))
    elif change=='missing-source':src._path('cancelled-1').unlink()
    elif change=='missing-destination':dst._path('cancelled-1').unlink()
    elif change=='lower-revision':
        path=src.pending_delete_root/'cancelled-1.json';data=json.loads(path.read_text())
        data['revision']=2;path.write_text(json.dumps(data))
    elif change=='different-receipt':
        path=src.pending_delete_root/'cancelled-1.json';data=json.loads(path.read_text());data['reason']='Different'
        (dst.pending_delete_root/path.name).write_text(json.dumps(data))
    elif change=='symlink':
        path=dst._path('cancelled-1');other=tmp_path/'foreign.md'
        other.write_bytes(path.read_bytes());path.unlink();path.symlink_to(other)
    elif change=='corrupt-body':dst._path('cancelled-1').write_text('corrupt')
    elif change in {'pending','applying'}:
        path=src.pending_delete_root/'cancelled-1.json';data=json.loads(path.read_text())
        data['status']='PENDING_DELETE' if change=='pending' else 'APPLYING_DELETE'
        if change=='applying':data['content_sha256']='0'*64
        path.write_text(json.dumps(data))
    else:
        folder=dst.history_root/'operations/unknown-v1';folder.mkdir(parents=True);(folder/'foreign.json').write_text('{}')
    before=fingerprints(tmp_path)
    result=import_deleted_receipts(source,destination,include_cancelled=True)
    assert result['status']=='BLOCKED' and result['imported']==[]
    assert fingerprints(tmp_path)==before
    assert not (dst.pending_delete_root/'cancelled-0.json').exists()


def test_cancelled_import_keeps_live_information_and_thread_links(tmp_path):
    source,destination,src,dst=seed(tmp_path)
    storage=ThreadStorage(dst.persistent_root)
    storage.create(Thread('project','Title','Goal',relations=[{'type':'CONCERNS','target_id':'cancelled-0'}]))
    before=dst._path('cancelled-0').read_bytes(),storage._path('project').read_bytes()
    assert import_deleted_receipts(source,destination,include_cancelled=True)['status']=='IMPORTED'
    assert (dst._path('cancelled-0').read_bytes(),storage._path('project').read_bytes())==before


def test_real_exit_after_first_receipt_resumes(tmp_path):
    source,destination,_,dst=seed(tmp_path)
    script='''
import os,sys
import core.migration.deleted_receipts as m
original=m._publish_receipt
def cut(path,raw):
 original(path,raw)
 os._exit(74)
m._publish_receipt=cut
m.import_deleted_receipts(sys.argv[1],sys.argv[2],include_cancelled=True)
'''
    process=subprocess.run([sys.executable,'-B','-c',script,str(source),str(destination)])
    assert process.returncode==74
    assert (dst.pending_delete_root/'cancelled-0.json').exists()
    assert import_deleted_receipts(source,destination,include_cancelled=True)['imported']==['cancelled-1']


def test_two_concurrent_importers_preserve_exact_receipts(tmp_path):
    source,destination,_,_=seed(tmp_path)
    script='''
import json,sys
from core.migration.deleted_receipts import import_deleted_receipts
print(json.dumps(import_deleted_receipts(sys.argv[1],sys.argv[2],include_cancelled=True)))
'''
    commands=[sys.executable,'-B','-c',script,str(source),str(destination)]
    processes=[subprocess.Popen(commands,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)]
    states=[]
    for process in processes:
        stdout,stderr=process.communicate(timeout=20)
        assert process.returncode==0,stderr
        states.append(json.loads(stdout)['status'])
    assert sorted(states)==['IMPORTED','UNCHANGED']


def test_cli_include_cancelled_is_explicit(tmp_path,capsys):
    source,destination,_,_=seed(tmp_path)
    common=['--source',str(source),'--destination',str(destination)]
    before=fingerprints(tmp_path)
    assert main(common)==1 and json.loads(capsys.readouterr().out)['status']=='BLOCKED'
    assert main([*common,'--include-cancelled'])==0 and json.loads(capsys.readouterr().out)['status']=='READY'
    assert fingerprints(tmp_path)==before
    assert main([*common,'--include-cancelled','--apply'])==0
    assert json.loads(capsys.readouterr().out)['status']=='IMPORTED'
