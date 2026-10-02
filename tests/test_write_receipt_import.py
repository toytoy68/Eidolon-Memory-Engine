"""Terminal replay receipts preserve commands and manual decisions across core copies."""
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys

import pytest

from core.backend.errors import RevisionConflict
from core.information.failed_resolution import review_failed_information, retry_failed_information
from core.migration.write_receipts import inspect_write_receipts, import_write_receipts, main
from core.operations.models import OperationStatus
from core.operations.readiness import check_readiness
from tests.test_failed_information_resolution import seed as seed_failed, retry as retry_failed
from tests.test_information_writes import service, memory, command
from tests.test_migration_converter import fingerprints


def seed(root, *, count=2, deleted=False, compact=True):
    source,destination=root/'source',root/'destination'
    src,dst=service(source),service(destination)
    for number in range(count):
        identity=f'info-{number}'
        target=replace(memory(),information_id=identity)
        src.create(target,**command(f'create-{number}'))
        src.update(replace(target,content=f'Edited {number}'),previous_revision=1,**command(f'update-{number}'))
        if compact:
            src.compact(f'create-{number}');src.compact(f'update-{number}')
        dst.backend.store(src.backend.get(identity))
        if deleted:
            src.backend.delete_request(identity,'human','Remove',2,f'delete-{number}')
            src.backend.approve_delete(identity,f'delete-{number}')
            dst.backend._path(identity).unlink()
            receipt=src.backend.pending_delete_root/f'{identity}.json'
            target_path=dst.backend.pending_delete_root/receipt.name
            target_path.write_bytes(receipt.read_bytes())
    return source,destination,src,dst


def test_preview_import_replay_preserves_exact_bytes_without_copying_bodies(tmp_path):
    source,destination,src,dst=seed(tmp_path)
    before=fingerprints(tmp_path)
    report=inspect_write_receipts(source,destination)
    assert report['status']=='READY' and len(report['receipts'])==4
    assert fingerprints(tmp_path)==before
    source_before=fingerprints(source)
    result=import_write_receipts(source,destination)
    assert result['status']=='IMPORTED' and len(result['imported'])==4
    assert fingerprints(source)==source_before
    assert check_readiness(destination)['ready']
    for opid in src.journal.ids():
        assert dst.journal.receipt_path(opid).read_bytes()==src.journal.receipt_path(opid).read_bytes()
        event_id=src.journal.read(opid).result['event_id']
        assert dst.events._path(event_id).read_bytes()==src.events._path(event_id).read_bytes()
        assert not dst.operations._path(opid).exists()
    current=dst.backend.get('info-0')
    assert dst.create(replace(memory(),information_id='info-0'),**command('create-0'))['revision']==1
    assert dst.backend.get('info-0')==current
    before=fingerprints(destination)
    assert import_write_receipts(source,destination)['status']=='UNCHANGED'
    assert fingerprints(destination)==before


def test_deleted_identity_and_replay_do_not_resurrect(tmp_path):
    source,destination,src,dst=seed(tmp_path,deleted=True)
    assert import_write_receipts(source,destination)['status']=='IMPORTED'
    assert dst.create(replace(memory(),information_id='info-0'),**command('create-0'))['revision']==1
    assert dst.backend.get('info-0') is None
    with pytest.raises(RevisionConflict):
        dst.backend.store(replace(memory(),information_id='info-0'))


def test_manual_resolution_history_replays_after_import(tmp_path,monkeypatch):
    source,destination=tmp_path/'source',tmp_path/'destination'
    src=seed_failed(source,monkeypatch);report=review_failed_information(source,'failed')
    result=retry_failed(source,report);src.compact('failed')
    dst=service(destination);dst.backend.store(src.backend.get('info-1'))
    assert import_write_receipts(source,destination)['status']=='IMPORTED'
    assert dst.journal.read('failed').receipt['manual_resolutions']==src.journal.read('failed').receipt['manual_resolutions']
    before=fingerprints(destination)
    assert retry_failed(destination,report)==result
    assert fingerprints(destination)==before


@pytest.mark.parametrize('change',['different-body','missing-body','event-bytes','receipt-bytes',
                                   'invalid-source-receipt','invalid-source-event','missing-source-event',
                                   'source-pending','destination-pending','source-unknown','source-symlink',
                                   'destination-symlink','uncompacted','deleted-reservation-missing',
                                   'source-body-without-deletion'])
def test_global_conflict_refuses_all_publications(tmp_path,change):
    source,destination,src,dst=seed(tmp_path,deleted=change=='deleted-reservation-missing',compact=change!='uncompacted')
    if change=='different-body':
        dst.backend._path('info-1').write_text(dst.backend._serialize_checked(replace(dst.backend.get('info-1'),content='Foreign')))
    elif change=='missing-body':
        dst.backend._path('info-1').unlink()
    elif change=='event-bytes':
        path=dst.events._path('event-update-1');path.write_bytes(src.events._path('event-update-1').read_bytes()+b'\n')
    elif change=='receipt-bytes':
        path=dst.journal.receipt_path('update-1');path.parent.mkdir(parents=True)
        path.write_bytes(src.journal.receipt_path('update-1').read_bytes()+b'\n')
        for event_id in ['event-update-1']:
            dst.events._path(event_id).write_bytes(src.events._path(event_id).read_bytes())
    elif change=='invalid-source-receipt':
        src.journal.receipt_path('update-1').write_text('{}')
    elif change=='invalid-source-event':
        src.events._path('event-update-1').write_text('corrupt')
    elif change=='missing-source-event':
        src.events._path('event-update-1').unlink()
    elif change in {'source-pending','destination-pending'}:
        writer=src if change=='source-pending' else dst
        original=writer._resume
        writer._resume=lambda *args: (_ for _ in ()).throw(RuntimeError('stopped'))
        with pytest.raises(RuntimeError):
            writer.create(replace(memory(),information_id='pending'),**command('pending'))
        writer._resume=original
    elif change=='source-unknown':
        folder=src.backend.history_root/'operations/unknown-v1';folder.mkdir();(folder/'bad.json').write_text('{}')
    elif change=='source-symlink':
        path=src.journal.receipt_path('update-1');other=tmp_path/'foreign.json'
        other.write_bytes(path.read_bytes());path.unlink();path.symlink_to(other)
    elif change=='destination-symlink':
        path=dst.events.events_root;path.rename(tmp_path/'foreign-events');path.symlink_to(tmp_path/'foreign-events')
    elif change=='deleted-reservation-missing':
        (dst.backend.pending_delete_root/'info-1.json').unlink()
    elif change=='source-body-without-deletion':
        src.backend._path('info-1').unlink();dst.backend._path('info-1').unlink()
    before=fingerprints(tmp_path)
    report=import_write_receipts(source,destination)
    assert report['status']=='BLOCKED' and report['imported']==[]
    assert fingerprints(tmp_path)==before
    assert not dst.journal.receipt_path('create-0').exists()


@pytest.mark.parametrize('shape',['same','nested-source','nested-destination','missing-destination','alias'])
def test_unsafe_or_uninitialized_trees_are_read_only(tmp_path,shape):
    source,destination,_,_=seed(tmp_path)
    if shape=='same':destination=source
    elif shape=='nested-source':source=destination/'nested'
    elif shape=='nested-destination':destination=source/'nested'
    elif shape=='missing-destination':destination=tmp_path/'missing'
    else:
        alias=tmp_path/'alias';alias.symlink_to(source,target_is_directory=True);source=alias
    before=fingerprints(tmp_path)
    assert inspect_write_receipts(source,destination)['status']=='BLOCKED'
    assert import_write_receipts(source,destination)['status']=='BLOCKED'
    assert fingerprints(tmp_path)==before


@pytest.mark.parametrize('boundary',['event','receipt'])
def test_process_exit_commits_prefix_and_rerun_finishes(tmp_path,boundary):
    source,destination,_,_=seed(tmp_path)
    script='''
import os,sys
import core.migration.write_receipts as m
original=m._publish_file
count=0
def cut(path,raw):
 global count
 original(path,raw)
 if (path.suffix=='.md' and sys.argv[3]=='event') or (path.suffix=='.json' and sys.argv[3]=='receipt'):
  os._exit(74)
m._publish_file=cut
m.import_write_receipts(sys.argv[1],sys.argv[2])
'''
    process=subprocess.run([sys.executable,'-B','-c',script,str(source),str(destination),boundary])
    assert process.returncode==74
    assert check_readiness(destination)['ready']
    result=import_write_receipts(source,destination)
    assert result['status']=='IMPORTED'
    assert inspect_write_receipts(source,destination)['status']=='UNCHANGED'


def test_two_importers_are_serialized(tmp_path):
    source,destination,_,_=seed(tmp_path)
    script='''
import sys,json
from core.migration.write_receipts import import_write_receipts
print(json.dumps(import_write_receipts(sys.argv[1],sys.argv[2])))
'''
    cmd=[sys.executable,'-B','-c',script,str(source),str(destination)]
    processes=[subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)]
    results=[]
    for process in processes:
        stdout,stderr=process.communicate(timeout=20)
        assert process.returncode==0,stderr
        results.append(json.loads(stdout)['status'])
    assert sorted(results)==['IMPORTED','UNCHANGED']


def test_revalidation_under_lock_blocks_changed_target(tmp_path,monkeypatch):
    source,destination,_,dst=seed(tmp_path)
    import core.migration.write_receipts as module
    from contextlib import contextmanager
    real=module.exclusive_write
    @contextmanager
    def changed(root):
        if Path(root)==dst.backend.persistent_root:
            dst.backend._path('info-1').write_text(dst.backend._serialize_checked(replace(dst.backend.get('info-1'),content='Foreign')))
        with real(root):
            yield
    monkeypatch.setattr(module,'exclusive_write',changed)
    assert import_write_receipts(source,destination)['status']=='BLOCKED'
    assert not dst.journal.receipt_path('create-0').exists()


def test_cli_preview_and_apply(tmp_path,capsys):
    source,destination,_,_=seed(tmp_path);before=fingerprints(tmp_path)
    args=['--source',str(source),'--destination',str(destination)]
    assert main(args)==0 and json.loads(capsys.readouterr().out)['status']=='READY'
    assert fingerprints(tmp_path)==before
    assert main([*args,'--apply'])==0 and json.loads(capsys.readouterr().out)['status']=='IMPORTED'


@pytest.mark.parametrize('field',['target','revision','type','cause'])
def test_matching_digest_cannot_hide_wrong_event_contract(tmp_path,field):
    source,destination,src,_=seed(tmp_path)
    from core.events.models import EventType,EventRelation,RelationType
    from core.information.write_journal import event_hash
    event=src.events.get('event-update-1')
    if field=='target':event=replace(event,information_id='info-0')
    elif field=='revision':event=replace(event,revision=99)
    elif field=='type':event=replace(event,event_type=EventType.CREATED)
    else:event=replace(event,relations=[EventRelation(RelationType.CAUSED_BY,'foreign')])
    src.events._path(event.event_id).write_text(src.events._serialize(event))
    path=src.journal.receipt_path('update-1');data=json.loads(path.read_text())
    data['event_sha256']=event_hash(event);path.write_text(json.dumps(data))
    assert check_readiness(source)['ready']
    before=fingerprints(tmp_path)
    assert import_write_receipts(source,destination)['status']=='BLOCKED'
    assert fingerprints(tmp_path)==before


def test_old_replay_revision_cannot_exceed_canonical_revision(tmp_path):
    source,destination,src,dst=seed(tmp_path)
    for writer in (src,dst):
        current=writer.backend.get('info-1')
        writer.backend._path('info-1').write_text(writer.backend._serialize_checked(replace(current,revision=1)))
    before=fingerprints(tmp_path)
    assert import_write_receipts(source,destination)['status']=='BLOCKED'
    assert fingerprints(tmp_path)==before


def test_process_exit_before_receipt_rename_leaves_blocking_residue(tmp_path):
    source,destination,_,_=seed(tmp_path)
    script='''
import os,sys
import core.migration.converter as converter
from core.migration.write_receipts import import_write_receipts
original=converter.os.replace
def cut(source,destination):
 if str(destination).endswith('.json'):
  os._exit(74)
 return original(source,destination)
converter.os.replace=cut
import_write_receipts(sys.argv[1],sys.argv[2])
'''
    process=subprocess.run([sys.executable,'-B','-c',script,str(source),str(destination)])
    assert process.returncode==74
    assert not check_readiness(destination)['ready']
    before=fingerprints(destination)
    assert import_write_receipts(source,destination)['status']=='BLOCKED'
    assert fingerprints(destination)==before
