"""A stopped core copy preserves commands and notes, with all-or-nothing publication."""
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.information.failed_resolution import review_failed_information
from core.information.writes import FilesystemInformationWrites
from core.lifecycle.service import LifecycleTriggers
from core.migration.core_copy import inspect_core_copy, copy_core, main
from core.operations.errors import OperationConflict
from core.operations.models import OperationStatus
from core.operations.readiness import check_readiness
from core.routing.execution import RoutingExecutor
from core.threads.models import ThreadStatus
from core.threads.service import ThreadService
from tests.test_failed_information_resolution import seed as seed_failed, retry as retry_failed
from tests.test_migration_converter import fingerprints
from tests.test_routing_execution import seed as route_seed, preview, execute
from tests.test_routing_new_project import fixture as new_fixture


def memory_files(root):
    return {key:value for key,value in fingerprints(root).items()
            if key.startswith('memory/') and not key.endswith('.write.lock')}


def seed(root):
    source,destination=root/'source',root/'destination'
    backend,executor,target=route_seed(source)
    prepared=preview(executor,target)
    result=execute(executor,prepared)
    threads=ThreadService.for_backend(backend)
    threads.update_thread('project',{'kind':'ADD_ACTION','action':{'action_id':'measure','description':'Measure efficiency','status':'PLANNED','metadata':{}}},previous_revision=2,
                       operation_id='add-action',event_id='action-event',actor='human',timestamp='2026-10-03T00:00:00Z')
    path=executor.dossiers._path('project')
    path.write_bytes(path.read_bytes()+b'\r\nHuman note, never reconstruct automatically.\r\n')
    (source/'secret-config.txt').write_text('Do not transfer configuration')
    return source,destination,backend,executor,prepared,result


def test_copy_preserves_threads_actions_revisions_notes_and_replay(tmp_path):
    source,destination,backend,executor,prepared,result=seed(tmp_path)
    original=memory_files(source);before=fingerprints(tmp_path)
    plan=inspect_core_copy(source,destination)
    assert plan['status']=='READY' and plan['files']>0
    assert fingerprints(tmp_path)==before and not destination.exists()
    source_before=fingerprints(source)
    copied=copy_core(source,destination)
    assert copied['status']=='COPIED' and memory_files(destination)==original
    assert fingerprints(source)==source_before
    assert check_readiness(destination)['ready']
    assert not (destination/'secret-config.txt').exists()
    assert not list(destination.rglob('.write.lock'))
    target_backend=FilesystemBackend(destination/'memory/persistent',destination/'memory/history')
    target_executor=RoutingExecutor(target_backend)
    assert target_executor.execute(prepared,intent_id='intent',actor='human',timestamp='2026-10-01T18:30:00Z')==result
    thread=target_executor.storage.get('project')
    assert thread==executor.storage.get('project') and thread.revision==3
    assert thread.actions[0].action_id=='measure'
    assert target_executor.dossiers._path('project').read_bytes()==executor.dossiers._path('project').read_bytes()
    before=memory_files(destination)
    assert ThreadService.for_backend(target_backend).update_thread('project',{'kind':'ADD_ACTION','action':{'action_id':'measure','description':'Measure efficiency','status':'PLANNED','metadata':{}}},previous_revision=2,
                       operation_id='add-action',event_id='action-event',actor='human',timestamp='2026-10-03T00:00:00Z')==thread
    assert memory_files(destination)==before
    assert copy_core(source,destination)['status']=='UNCHANGED'


@pytest.mark.parametrize('state',['pending','cancelled','deleted'])
def test_preserves_deletion_states_without_approval_or_resurrection(tmp_path,state):
    source,destination=tmp_path/'source',tmp_path/'destination'
    backend=FilesystemBackend(source/'memory/persistent',source/'memory/history')
    backend.store(Memory('one',content='Body'))
    backend.delete_request('one','human','Review',1,'delete-one')
    if state=='cancelled':backend.cancel_delete('one','delete-one')
    elif state=='deleted':backend.approve_delete('one','delete-one')
    before=memory_files(source)
    assert copy_core(source,destination)['status']=='COPIED'
    assert memory_files(destination)==before
    path=destination/'memory/history/pending-delete/one.json'
    assert json.loads(path.read_text())['status']=={'pending':'PENDING_DELETE','cancelled':'CANCELLED','deleted':'DELETED'}[state]
    assert (destination/'memory/persistent/one.md').exists()==(state!='deleted')


def test_preserves_manual_audit_compact_receipt_and_deleted_replay(tmp_path,monkeypatch):
    source,destination=tmp_path/'source',tmp_path/'destination'
    writer=seed_failed(source,monkeypatch);report=review_failed_information(source,'failed')
    result=retry_failed(source,report);writer.compact('failed')
    writer.backend.delete_request('info-1','human','Remove',1,'delete')
    writer.backend.approve_delete('info-1','delete')
    assert copy_core(source,destination)['status']=='COPIED'
    before=memory_files(destination)
    assert retry_failed(destination,report)==result
    assert memory_files(destination)==before
    assert not (destination/'memory/persistent/info-1.md').exists()


@pytest.mark.parametrize('state',['scheduled','completed','cancelled'])
def test_preserves_lifecycle_schedule_without_dispatching(tmp_path,state):
    source,destination=tmp_path/'source',tmp_path/'destination'
    from tests.test_lifecycle_triggers import seed as trigger_seed, schedule, DUE, SCOPE, CREATED
    backend,service,_=trigger_seed(source)
    schedule(service)
    if state=='completed':service.run_due(at=DUE,query_scope=SCOPE)
    elif state=='cancelled':service.cancel('wake',actor='human',at=CREATED,reason='Not needed')
    before=memory_files(source)
    assert copy_core(source,destination)['status']=='COPIED'
    assert memory_files(destination)==before
    assert json.loads((destination/'memory/history/operations/lifecycle-trigger-v1/wake.json').read_text())['status']==state.upper()
    assert check_readiness(destination)['ready']


def test_new_project_parent_receipt_is_portable_without_reexecution(tmp_path):
    source,destination=tmp_path/'source',tmp_path/'destination'
    backend,executor,memory,project,context=new_fixture(source)
    prepared=executor.preview_new_project(memory,context,project=project)
    result=execute(executor,prepared)
    assert copy_core(source,destination)['status']=='COPIED'
    backend2=FilesystemBackend(destination/'memory/persistent',destination/'memory/history')
    executor2=RoutingExecutor(backend2)
    before=memory_files(destination)
    assert execute(executor2,prepared)==result and memory_files(destination)==before


@pytest.mark.parametrize('change',['legacy-information','corrupt-information','corrupt-thread','orphan-link',
 'failed-journal','applying-parent','unknown-history','symlink-file','symlink-directory','fifo','bad-dossier-path'])
def test_bad_source_refuses_before_destination_or_stage_creation(tmp_path,monkeypatch,change):
    source,destination,backend,executor,prepared,_=seed(tmp_path)
    if change=='legacy-information':backend._path('initial').write_text('---\ninformation_id: initial\n---\nlegacy')
    elif change=='corrupt-information':backend._path('initial').write_text('# Eidolon Information Object\n\nVersion: 0.2\nBroken')
    elif change=='corrupt-thread':executor.storage._path('project').write_text('corrupt')
    elif change=='orphan-link':backend._path('initial').unlink()
    elif change=='failed-journal':
        path=source/'memory/history/operations/thread-update-v1/add-action.json'
        data=json.loads(path.read_text());data['status']='FAILED';path.write_text(json.dumps(data))
    elif change=='applying-parent':
        edited=replace(backend.get('second'),content='Later input')
        from core.routing.policy import TargetRevision
        next_plan=preview(executor,edited,3,update_target=TargetRevision('second',1))
        with monkeypatch.context() as patch:
            patch.setattr(executor,'_checkpoint',lambda stage: (_ for _ in ()).throw(RuntimeError('stopped')))
            with pytest.raises(RuntimeError):execute(executor,next_plan,'next')
    elif change=='unknown-history':
        folder=source/'memory/history/operations/foreign-v1';folder.mkdir();(folder/'foreign.json').write_text('{}')
    elif change=='symlink-file':
        path=backend._path('initial');other=tmp_path/'outside.md'
        other.write_bytes(path.read_bytes());path.unlink();path.symlink_to(other)
    elif change=='symlink-directory':
        folder=source/'memory/dossiers';folder.rename(tmp_path/'outside-dossiers');folder.symlink_to(tmp_path/'outside-dossiers')
    elif change=='fifo':
        import os
        os.mkfifo(source/'memory/dossiers/pipe')
    else:
        # An unsafe supplemental entry must not disappear silently in a core transfer.
        (source/'memory/dossiers/unreadable').mkdir()
        (source/'memory/dossiers/unreadable/link').symlink_to(tmp_path/'missing')
    before=memory_files(source) if change!='fifo' else None
    result=copy_core(source,destination)
    assert result['status']=='BLOCKED' and not destination.exists()
    assert not (destination.parent/('.'+destination.name+'.core-copy-v1')).exists()
    if before is not None:assert memory_files(source)==before


@pytest.mark.parametrize('shape',['existing-empty','existing-data','same','nested','alias','parent-missing'])
def test_destination_is_never_overwritten(tmp_path,shape):
    source,destination,_,_,_,_=seed(tmp_path)
    if shape=='existing-empty':destination.mkdir()
    elif shape=='existing-data':destination.mkdir();(destination/'existing').write_text('Keep')
    elif shape=='same':destination=source
    elif shape=='nested':destination=source/'nested'
    elif shape=='alias':destination.symlink_to(tmp_path/'elsewhere')
    else:destination=tmp_path/'missing-parent'/'destination'
    before=fingerprints(tmp_path)
    assert inspect_core_copy(source,destination)['status']=='BLOCKED'
    assert copy_core(source,destination)['status']=='BLOCKED'
    assert fingerprints(tmp_path)==before


@pytest.mark.parametrize('boundary',['after_plan','after_file','before_publication','after_publication'])
def test_process_exit_never_exposes_partial_destination_and_resumes(tmp_path,boundary):
    source,destination,_,_,_,_=seed(tmp_path)
    script='''
import os,sys
import core.migration.core_copy as m
m._checkpoint=lambda stage,path=None: os._exit(74) if stage==sys.argv[3] else None
m.copy_core(sys.argv[1],sys.argv[2])
'''
    process=subprocess.run([sys.executable,'-B','-c',script,str(source),str(destination),boundary])
    assert process.returncode==74
    assert destination.exists()==(boundary=='after_publication')
    if destination.exists():assert memory_files(destination)==memory_files(source)
    result=copy_core(source,destination)
    assert result['status']==('UNCHANGED' if boundary=='after_publication' else 'COPIED')
    assert memory_files(destination)==memory_files(source)


def test_source_change_after_plan_blocks_without_publication(tmp_path,monkeypatch):
    source,destination,backend,_,_,_=seed(tmp_path)
    import core.migration.core_copy as module
    def changed(stage,path=None):
        if stage=='after_plan':
            backend._path('initial').write_text(backend._serialize_checked(replace(backend.get('initial'),content='Changed')))
    monkeypatch.setattr(module,'_checkpoint',changed)
    assert copy_core(source,destination)['status']=='BLOCKED'
    assert not destination.exists()


@pytest.mark.parametrize('change',['staged-file','unknown-stage','stage-plan','stage-link'])
def test_divergent_or_unknown_stage_is_not_adopted(tmp_path,change):
    source,destination,_,_,_,_=seed(tmp_path)
    script='''
import os,sys
import core.migration.core_copy as m
m._checkpoint=lambda stage,path=None: os._exit(74) if stage=='after_file' else None
m.copy_core(sys.argv[1],sys.argv[2])
'''
    process=subprocess.run([sys.executable,'-B','-c',script,str(source),str(destination)])
    assert process.returncode==74
    stage=destination.parent/('.'+destination.name+'.core-copy-v1')
    if change=='staged-file':next((stage/'tree/memory').rglob('*.md')).write_text('Foreign bytes')
    elif change=='unknown-stage':(stage/'unknown').write_text('Keep unknown')
    elif change=='stage-plan':
        path=stage/'plan.json';data=json.loads(path.read_text());data['source']='foreign';path.write_text(json.dumps(data))
    else:
        folder=stage/'tree/memory';folder.rename(tmp_path/'foreign-memory');folder.symlink_to(tmp_path/'foreign-memory')
    before=fingerprints(tmp_path)
    assert copy_core(source,destination)['status']=='BLOCKED' and not destination.exists()
    assert fingerprints(tmp_path)==before


def test_two_concurrent_copy_requests_publish_once(tmp_path):
    source,destination,_,_,_,_=seed(tmp_path)
    script='''
import sys,json
from core.migration.core_copy import copy_core
print(json.dumps(copy_core(sys.argv[1],sys.argv[2])))
'''
    commands=[sys.executable,'-B','-c',script,str(source),str(destination)]
    processes=[subprocess.Popen(commands,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)]
    statuses=[]
    for process in processes:
        stdout,stderr=process.communicate(timeout=20)
        assert process.returncode==0,stderr
        statuses.append(json.loads(stdout)['status'])
    assert sorted(statuses)==['COPIED','UNCHANGED']


def test_replay_refuses_source_or_destination_changed(tmp_path):
    source,destination,backend,_,_,_=seed(tmp_path)
    assert copy_core(source,destination)['status']=='COPIED'
    path=destination/'memory/persistent/initial.md';path.write_bytes(path.read_bytes()+b'\n')
    before=fingerprints(tmp_path)
    assert copy_core(source,destination)['status']=='BLOCKED' and fingerprints(tmp_path)==before
    path.write_bytes(backend._path('initial').read_bytes())
    backend._path('initial').write_bytes(backend._path('initial').read_bytes()+b'\n')
    before=fingerprints(tmp_path)
    assert copy_core(source,destination)['status']=='BLOCKED' and fingerprints(tmp_path)==before


def test_cli_preview_and_apply_are_explicit(tmp_path,capsys):
    source,destination,_,_,_,_=seed(tmp_path);before=fingerprints(tmp_path)
    args=['--source',str(source),'--destination',str(destination)]
    assert main(args)==0 and json.loads(capsys.readouterr().out)['status']=='READY'
    assert fingerprints(tmp_path)==before
    assert main([*args,'--apply'])==0 and json.loads(capsys.readouterr().out)['status']=='COPIED'


def test_destination_created_at_publication_is_never_replaced(tmp_path,monkeypatch):
    source,destination,_,_,_,_=seed(tmp_path)
    import core.migration.core_copy as module
    def intervene(stage,path=None):
        if stage=='before_publication':destination.mkdir()
    monkeypatch.setattr(module,'_checkpoint',intervene)
    assert copy_core(source,destination)['status']=='BLOCKED'
    assert destination.is_dir() and list(destination.iterdir())==[]


def test_staging_changed_at_publication_is_not_published(tmp_path,monkeypatch):
    source,destination,_,_,_,_=seed(tmp_path)
    import core.migration.core_copy as module
    def intervene(stage,path=None):
        if stage=='before_publication':
            path=destination.parent/('.'+destination.name+'.core-copy-v1')/'tree/memory/persistent/initial.md'
            path.write_text('foreign')
    monkeypatch.setattr(module,'_checkpoint',intervene)
    assert copy_core(source,destination)['status']=='BLOCKED'
    assert not destination.exists()


@pytest.mark.parametrize('relative,body',[
 ('memory/history/events/legacy.md','event_id: old\nevent_type: STORE\n'),
 ('memory/working/legacy.md','---\ninformation_id: legacy\n---\nOld input'),
])
def test_known_legacy_formats_require_conversion(tmp_path,relative,body):
    source,destination,_,_,_,_=seed(tmp_path)
    path=source/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(body)
    before=fingerprints(tmp_path)
    assert copy_core(source,destination)['status']=='BLOCKED'
    assert fingerprints(tmp_path)==before
