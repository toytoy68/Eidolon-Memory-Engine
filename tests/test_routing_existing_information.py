"""An explicit NONE journey links an existing Information without rewriting it."""
from copy import deepcopy
from dataclasses import asdict,replace
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from core.backend.filesystem import FilesystemBackend
from core.information.writes import FilesystemInformationWrites
from core.migration.core_copy import copy_core
from core.migration.inventory import inventory
from core.operations.errors import OperationConflict
from core.operations.readiness import check_readiness,recover_all
from core.routing.execution import RoutingExecutor
from core.routing.execution_cli import main
from core.routing.policy import RoutingContext
from core.threads.models import ThreadStatus
from core.threads.service import ThreadService
from tests.test_migration_converter import fingerprints
from tests.test_routing_execution import seed as route_seed,execute,STAMP


def seed(root):
    backend,executor,memory=route_seed(root)
    memory=replace(memory,metadata=dict(memory.metadata,availability='LOW'),
                   temporal=dict(memory.temporal,resume_at='2026-10-04T12:00:00Z'))
    writer=FilesystemInformationWrites(backend)
    writer.create(memory,operation_id='stored',event_id='stored-event',actor='human',timestamp=STAMP)
    return backend,executor,memory,writer


def preview(executor,memory,revision=1,**changes):
    context=RoutingContext(query_scope={'goal':'efficiency'},already_stored=True,existing_dossier='project',**changes)
    return executor.preview_link(memory,context,project_revision=revision)


def test_link_preserves_information_bytes_revision_events_and_lifecycle(tmp_path):
    backend,executor,memory,writer=seed(tmp_path)
    path=backend._path('second');path.write_bytes(path.read_bytes()+b'\r\n')
    before=fingerprints(tmp_path);prepared=preview(executor,memory)
    assert prepared['format_version']==4 and prepared['policy']['persistence']=='NONE'
    assert fingerprints(tmp_path)==before
    info_bytes=path.read_bytes();journal=fingerprints(writer.operations.root);events=fingerprints(writer.events.events_root)
    result=execute(executor,prepared)
    assert result['information']=={'id':'second','revision':1}
    assert result['project']=={'id':'project','revision':2} and result['deferred']==['availability']
    assert 'lifecycle' not in result and backend.get('second')==memory and path.read_bytes()==info_bytes
    assert fingerprints(writer.operations.root)==journal and fingerprints(writer.events.events_root)==events
    assert executor.storage._concerns(executor.storage.get('project'))=={'initial','second'}
    assert executor.dossiers.status('project')['status']=='CURRENT'
    assert not list((backend.history_root/'operations/lifecycle-trigger-v1').glob('*.json'))
    assert inventory(tmp_path)['categories']['routing_executions']=={'routing_execution_v4':1}
    assert check_readiness(tmp_path)['ready']
    receipt=executor.journal.path('intent').read_text()
    assert memory.content not in receipt
    before=fingerprints(tmp_path)
    assert execute(executor,prepared)==result and fingerprints(tmp_path)==before


@pytest.mark.parametrize('change',['different-content','different-metadata','different-revision','unqualified','ambiguous','removal','wrong-project-revision','wrong-dossier','not-already-stored','update-target'])
def test_preview_refuses_impossible_or_reinterpreted_links(tmp_path,change):
    backend,executor,memory,_=seed(tmp_path)
    context=RoutingContext(already_stored=True,existing_dossier='project');revision=1
    if change=='different-content':memory=replace(memory,content='Other text')
    elif change=='different-metadata':memory=replace(memory,metadata=dict(memory.metadata,availability='HIGH'))
    elif change=='different-revision':memory=replace(memory,revision=2)
    elif change=='unqualified':memory=replace(memory,metadata={})
    elif change=='ambiguous':context=replace(context,candidate_projects=('other','third'))
    elif change=='removal':context=replace(context,removal_observed=True)
    elif change=='wrong-project-revision':revision=2
    elif change=='wrong-dossier':context=replace(context,existing_dossier='other')
    elif change=='not-already-stored':context=replace(context,already_stored=False)
    else:
        from core.routing.policy import TargetRevision
        context=replace(context,update_target=TargetRevision('second',1))
    before=fingerprints(tmp_path)
    with pytest.raises(OperationConflict):executor.preview_link(memory,context,project_revision=revision)
    assert fingerprints(tmp_path)==before


@pytest.mark.parametrize('change',['information','project','pending-delete','missing','unknown-journal'])
def test_stale_or_reserved_inputs_refuse_before_parent_and_child_commands(tmp_path,change):
    backend,executor,memory,writer=seed(tmp_path);prepared=preview(executor,memory)
    if change=='information':writer.update(replace(memory,content='Correction'),previous_revision=1,operation_id='correction',event_id='corrected',actor='human',timestamp=STAMP)
    elif change=='project':ThreadService.for_backend(backend).change_status('project',ThreadStatus.VALIDATED,previous_revision=1,operation_id='status',event_id='status-event')
    elif change=='pending-delete':backend.delete_request('second','human','Review',1,'delete')
    elif change=='missing':backend._path('second').unlink()
    else:
        path=backend.history_root/'operations/foreign/one.json';path.parent.mkdir();path.write_text('{}')
    content=backend._path('second').read_bytes() if backend._path('second').exists() else None
    project=executor.storage.get('project')
    with pytest.raises(OperationConflict):execute(executor,prepared)
    assert executor.journal.read('intent') is None and executor.storage.get('project')==project
    assert (backend._path('second').read_bytes() if backend._path('second').exists() else None)==content
    assert not writer.operations._path(executor.child_id('intent','information')).exists()


@pytest.mark.parametrize('stage',['before_information','after_information','after_project','after_projection'])
def test_interrupted_link_reserves_targets_and_global_recovery_finishes(tmp_path,monkeypatch,stage):
    backend,executor,memory,writer=seed(tmp_path);prepared=preview(executor,memory)
    def stopped(boundary):
        if boundary==stage:raise RuntimeError('stopped')
    with monkeypatch.context() as patch:
        patch.setattr(executor,'_checkpoint',stopped)
        with pytest.raises(RuntimeError):execute(executor,prepared)
    assert not check_readiness(tmp_path)['ready']
    with pytest.raises(OperationConflict):writer.update(replace(memory,content='Other'),previous_revision=1,operation_id='other',event_id='other-event',actor='human',timestamp=STAMP)
    assert recover_all(tmp_path)['readiness']['ready']
    result=execute(executor,prepared)
    assert result['information']['revision']==1 and backend.get('second')==memory
    assert executor.storage.get('project').revision==2
    assert not writer.operations._path(executor.child_id('intent','information')).exists()


@pytest.mark.parametrize('stage',['after_information','after_project','after_projection'])
def test_real_process_exit_link_recovers_without_information_effect(tmp_path,stage):
    backend,executor,memory,_=seed(tmp_path);prepared=preview(executor,memory)
    plan_path=tmp_path/'plan.json';plan_path.write_text(json.dumps(prepared));before=backend._path('second').read_bytes()
    script='''
import os,sys,json
from pathlib import Path
from core.backend.filesystem import FilesystemBackend
from core.routing.execution import RoutingExecutor
root=Path(sys.argv[1]);executor=RoutingExecutor(FilesystemBackend(root/'memory/persistent',root/'memory/history'))
executor._checkpoint=lambda stage: os._exit(74) if stage==sys.argv[3] else None
executor.execute(json.loads(Path(sys.argv[2]).read_text()),intent_id='intent',actor='human',timestamp='2026-10-01T18:30:00Z')
'''
    process=subprocess.run([sys.executable,'-B','-c',script,str(tmp_path),str(plan_path),stage])
    assert process.returncode==74
    assert recover_all(tmp_path)['readiness']['ready']
    assert execute(executor,prepared)['information']['revision']==1 and backend._path('second').read_bytes()==before


def test_already_linked_project_has_no_extra_revision_or_event(tmp_path):
    backend,executor,memory,_=seed(tmp_path)
    execute(executor,preview(executor,memory))
    prepared=preview(executor,memory,2)
    events=fingerprints(backend.history_root/'events/thread-update-v1')
    result=execute(executor,prepared,'again')
    assert result['project']['revision']==2 and executor.storage.get('project').revision==2
    assert fingerprints(backend.history_root/'events/thread-update-v1')==events


def test_terminal_link_replay_does_not_undo_information_edits_or_recreate_project(tmp_path):
    backend,executor,memory,writer=seed(tmp_path);prepared=preview(executor,memory)
    result=execute(executor,prepared)
    writer.update(replace(memory,content='Edited later'),previous_revision=1,operation_id='later',event_id='later-event',actor='human',timestamp=STAMP)
    ThreadService.for_backend(backend).delete('project',previous_revision=2,operation_id='delete-project')
    before=fingerprints(tmp_path)
    assert execute(executor,prepared)==result and fingerprints(tmp_path)==before
    assert backend.get('second').revision==2 and executor.storage.get('project') is None


def test_format_four_core_copy_keeps_exact_parent_replay(tmp_path):
    source,destination=tmp_path/'source',tmp_path/'clone'
    backend,executor,memory,_=seed(source);prepared=preview(executor,memory);result=execute(executor,prepared)
    assert copy_core(source,destination)['status']=='COPIED'
    other=RoutingExecutor(FilesystemBackend(destination/'memory/persistent',destination/'memory/history'))
    before={key:value for key,value in fingerprints(destination).items() if not key.endswith('.write.lock')}
    assert execute(other,prepared)==result
    assert {key:value for key,value in fingerprints(destination).items() if not key.endswith('.write.lock')}==before


def test_two_concurrent_links_same_intent_apply_once(tmp_path):
    backend,executor,memory,_=seed(tmp_path);prepared=preview(executor,memory)
    plan_path=tmp_path/'plan.json';plan_path.write_text(json.dumps(prepared))
    script='''
import sys,json
from pathlib import Path
from core.backend.filesystem import FilesystemBackend
from core.routing.execution import RoutingExecutor
root=Path(sys.argv[1]);executor=RoutingExecutor(FilesystemBackend(root/'memory/persistent',root/'memory/history'))
print(json.dumps(executor.execute(json.loads(Path(sys.argv[2]).read_text()),intent_id='intent',actor='human',timestamp='2026-10-01T18:30:00Z')))
'''
    command=[sys.executable,'-B','-c',script,str(tmp_path),str(plan_path)]
    processes=[subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)]
    results=[]
    for process in processes:
        stdout,stderr=process.communicate(timeout=20);assert process.returncode==0,stderr;results.append(json.loads(stdout))
    assert results[0]==results[1] and executor.storage.get('project').revision==2 and backend.get('second')==memory


def test_assessment_points_to_explicit_link_preview(tmp_path):
    _,executor,memory,_=seed(tmp_path)
    result=executor.assess(memory,RoutingContext(already_stored=True,existing_dossier='project'))
    assert result['status']=='PREVIEW_REQUIRED' and result['next_step']=='PREVIEW_LINK_EXISTING'
    assert result['execution_validated'] is False


def test_cli_link_only_preview_and_execute(tmp_path,capsys):
    backend,executor,memory,_=seed(tmp_path)
    memory_path=tmp_path/'input.json';context_path=tmp_path/'context.json';plan_path=tmp_path/'plan.json'
    memory_path.write_text(json.dumps(asdict(memory)));context_path.write_text(json.dumps(asdict(RoutingContext(already_stored=True,existing_dossier='project'))))
    before=fingerprints(tmp_path)
    args=['--root',str(tmp_path),'preview','--memory',str(memory_path),'--context',str(context_path),'--project-revision','1','--link-only']
    assert main(args)==0
    prepared=json.loads(capsys.readouterr().out);assert prepared['format_version']==4 and fingerprints(tmp_path)==before
    plan_path.write_text(json.dumps(prepared))
    assert main(['--root',str(tmp_path),'execute','--plan',str(plan_path),'--intent-id','intent','--actor','human','--timestamp',STAMP])==0
    assert json.loads(capsys.readouterr().out)['information']['revision']==1


def test_foreign_information_child_blocks_before_parent_reservation(tmp_path):
    from core.backend.models import Memory
    backend,executor,memory,writer=seed(tmp_path);prepared=preview(executor,memory)
    writer.create(Memory('foreign',content='Other'),operation_id=executor.child_id('intent','information'),
                  event_id='foreign-event',actor='human',timestamp=STAMP)
    with pytest.raises(OperationConflict):execute(executor,prepared)
    assert executor.journal.read('intent') is None and executor.storage.get('project').revision==1


def test_link_refresh_keeps_human_notes_verbatim(tmp_path):
    _,executor,memory,_=seed(tmp_path)
    executor.dossiers.rebuild('project');path=executor.dossiers._path('project')
    note=b'Personal decision.\r\nWait for measured evidence.'
    data=path.read_bytes().replace('Écrire ici les notes humaines non ingérées.'.encode(),note)
    path.write_bytes(data)
    execute(executor,preview(executor,memory))
    assert note in path.read_bytes() and executor.dossiers.status('project')['status']=='CURRENT'


def test_tampered_memory_in_link_plan_cannot_replace_canonical_body(tmp_path):
    backend,executor,memory,_=seed(tmp_path);prepared=preview(executor,memory)
    prepared['memory']['content']='Injected replacement'
    before=backend._path('second').read_bytes()
    with pytest.raises(OperationConflict):execute(executor,prepared)
    assert backend._path('second').read_bytes()==before and executor.journal.read('intent') is None


def test_link_cli_refuses_lifecycle_option_without_writes(tmp_path,capsys):
    _,executor,memory,_=seed(tmp_path)
    memory_path=tmp_path/'input.json';context_path=tmp_path/'context.json'
    memory_path.write_text(json.dumps(asdict(memory)));context_path.write_text(json.dumps(asdict(RoutingContext(already_stored=True,existing_dossier='project'))))
    before=fingerprints(tmp_path)
    assert main(['--root',str(tmp_path),'preview','--memory',str(memory_path),'--context',str(context_path),'--project-revision','1','--link-only','--with-lifecycle'])==1
    assert json.loads(capsys.readouterr().out)['status']=='BLOCKED' and fingerprints(tmp_path)==before
