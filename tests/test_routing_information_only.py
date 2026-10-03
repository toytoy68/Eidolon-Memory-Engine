"""An explicit no-dossier journey persists qualified memory and its deadline."""
from dataclasses import asdict,replace
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.information.writes import FilesystemInformationWrites
from core.lifecycle.service import LifecycleTriggers
from core.migration.core_copy import copy_core
from core.migration.inventory import inventory
from core.operations.errors import OperationConflict
from core.operations.readiness import check_readiness,recover_all
from core.routing.execution import RoutingExecutor
from core.routing.execution_cli import main
from core.routing.policy import RoutingContext,TargetRevision
from core.threads.models import Thread
from core.threads.storage import ThreadStorage
from tests.test_migration_converter import fingerprints

STAMP='2026-10-03T01:00:00Z'
DUE='2026-10-04T01:00:00Z'
SCOPE={'goal':'efficiency'}


def seed(root):
    backend=FilesystemBackend(root/'memory/persistent',root/'memory/history')
    memory=Memory('one',content='Measurement',metadata={'epistemic_status':'UNVERIFIED',
        'qualification':{'version':'0.1','nature':'TECHNICAL','qualified_by':'human'},
        'context':{'scope':SCOPE}},provenance={'source':'human','author_role':'ADMIN'})
    return backend,RoutingExecutor(backend),memory


def preview(executor,memory,**changes):
    return executor.preview_information(memory,RoutingContext(query_scope=SCOPE,**changes))


def execute(executor,prepared,intent='intent'):
    return executor.execute(prepared,intent_id=intent,actor='human',timestamp=STAMP)


def test_no_dossier_route_persists_qualified_information_without_project(tmp_path):
    backend,executor,memory=seed(tmp_path);before=fingerprints(tmp_path)
    prepared=preview(executor,memory)
    assert prepared['format_version']==5 and prepared['project_before'] is None
    assert fingerprints(tmp_path)==before
    result=execute(executor,prepared)
    assert result['information']=={'id':'one','revision':1} and result['project'] is None
    assert result['projection_digest'] is None and result['deferred']==[]
    assert result['lifecycle']=={'availability':'INTERMEDIATE','trigger_id':None}
    assert backend.get('one')==replace(memory,metadata=dict(memory.metadata,availability='INTERMEDIATE'))
    assert not list((backend.persistent_root/'threads').glob('*.md')) and not (tmp_path/'memory/dossiers').exists()
    assert check_readiness(tmp_path)['ready']
    assert inventory(tmp_path)['categories']['routing_executions']=={'routing_execution_v5':1}
    assert memory.content not in executor.journal.path('intent').read_text()
    before=fingerprints(tmp_path)
    assert execute(executor,prepared)==result and fingerprints(tmp_path)==before


def test_scheduled_source_registers_exact_deadline_without_truth_promotion(tmp_path):
    backend,executor,memory=seed(tmp_path)
    memory=replace(memory,temporal={'resume_at':DUE})
    result=execute(executor,preview(executor,memory));trigger=result['lifecycle']['trigger_id']
    record=LifecycleTriggers(backend).journal.read(trigger)
    assert record['status']=='SCHEDULED' and record['command']['due_at']==DUE
    assert record['command']['revision']==1 and backend.get('one').metadata['epistemic_status']=='UNVERIFIED'
    assert LifecycleTriggers(backend).run_due(at=DUE,query_scope=SCOPE)[trigger]['result']['reason']=='RECHECK'
    assert backend.get('one').revision==2 and backend.get('one').metadata['epistemic_status']=='UNVERIFIED'


def test_update_without_project_uses_canonical_cas_and_one_new_revision(tmp_path):
    backend,executor,memory=seed(tmp_path)
    execute(executor,preview(executor,memory))
    current=backend.get('one');edited=replace(current,content='Corrected')
    prepared=preview(executor,edited,update_target=TargetRevision('one',1))
    result=execute(executor,prepared,'update')
    assert result['information']['revision']==2 and backend.get('one').content=='Corrected'
    assert not list((backend.persistent_root/'threads').glob('*.md'))
    before=fingerprints(tmp_path)
    assert execute(executor,prepared,'update')==result and fingerprints(tmp_path)==before


@pytest.mark.parametrize('change',['unqualified','none','project','place','topic','ambiguous','removal','wrong-update','invalid-date','requested-dossier','unresolved'])
def test_unsupported_or_review_plans_are_refused_without_initialization(tmp_path,change):
    backend,executor,memory=seed(tmp_path);context=RoutingContext(query_scope=SCOPE)
    if change=='unqualified':memory=replace(memory,metadata={})
    elif change=='none':context=replace(context,already_stored=True)
    elif change in {'project','place','topic'}:memory=replace(memory,metadata=dict(memory.metadata,context=dict(memory.metadata['context'],**{change+'_id':'chosen'})))
    elif change=='ambiguous':context=replace(context,candidate_projects=('one','two'))
    elif change=='removal':context=replace(context,removal_observed=True)
    elif change=='wrong-update':context=replace(context,update_target=TargetRevision('other',1))
    elif change=='invalid-date':memory=replace(memory,temporal={'resume_at':'tomorrow'})
    elif change=='requested-dossier':context=replace(context,existing_dossier='chosen')
    else:context=replace(context,unresolved_conflict=True)
    before=fingerprints(tmp_path)
    with pytest.raises(OperationConflict):executor.preview_information(memory,context)
    assert fingerprints(tmp_path)==before


@pytest.mark.parametrize('stage',['before_information','after_information','after_trigger'])
def test_interrupted_information_route_recovers_and_reserves_only_information(tmp_path,monkeypatch,stage):
    backend,executor,memory=seed(tmp_path);memory=replace(memory,temporal={'resume_at':DUE})
    prepared=preview(executor,memory)
    storage=ThreadStorage(backend.persistent_root)
    storage.create(Thread('unrelated','Other','Goal',created_at=STAMP,updated_at=STAMP))
    def stop(boundary):
        if boundary==stage:raise RuntimeError('stop')
    with monkeypatch.context() as patch:
        patch.setattr(executor,'_checkpoint',stop)
        with pytest.raises(RuntimeError):execute(executor,prepared)
    assert not check_readiness(tmp_path)['ready']
    # A no-project owner must not reserve every Thread by comparing None == None.
    from core.routing.execution_journal import require_available
    require_available(backend.history_root,thread_id='unrelated')
    with pytest.raises(OperationConflict):require_available(backend.history_root,information_id='one')
    report=recover_all(tmp_path)
    assert report['readiness']['ready']
    result=execute(executor,prepared)
    assert backend.get('one').revision==1 and LifecycleTriggers(backend).journal.read(result['lifecycle']['trigger_id'])['status']=='SCHEDULED'
    assert storage.get('unrelated').revision==1


@pytest.mark.parametrize('stage',['after_information','after_trigger'])
def test_real_process_exit_recovers_on_tree_without_threads(tmp_path,stage):
    backend,executor,memory=seed(tmp_path);memory=replace(memory,temporal={'resume_at':DUE})
    prepared=preview(executor,memory);path=tmp_path/'plan.json';path.write_text(json.dumps(prepared))
    script='''
import os,sys,json
from pathlib import Path
from core.backend.filesystem import FilesystemBackend
from core.routing.execution import RoutingExecutor
root=Path(sys.argv[1]);executor=RoutingExecutor(FilesystemBackend(root/'memory/persistent',root/'memory/history'))
executor._checkpoint=lambda stage: os._exit(74) if stage==sys.argv[3] else None
executor.execute(json.loads(Path(sys.argv[2]).read_text()),intent_id='intent',actor='human',timestamp='2026-10-03T01:00:00Z')
'''
    process=subprocess.run([sys.executable,'-B','-c',script,str(tmp_path),str(path),stage])
    assert process.returncode==74 and executor.recover()['intent']['status']=='COMMITTED'
    assert check_readiness(tmp_path)['ready'] and backend.get('one').revision==1
    assert not list((backend.persistent_root/'threads').glob('*.md'))


def test_stale_information_snapshot_or_reserved_deletion_blocks_before_intention(tmp_path):
    backend,executor,memory=seed(tmp_path)
    execute(executor,preview(executor,memory))
    current=backend.get('one');prepared=preview(executor,replace(current,content='Correction'),update_target=TargetRevision('one',1))
    backend.delete_request('one','human','Review',1,'delete')
    with pytest.raises(OperationConflict):execute(executor,prepared,'update')
    assert executor.journal.read('update') is None and backend.get('one')==current


def test_terminal_replay_after_compaction_and_deletion_never_resurrects(tmp_path):
    backend,executor,memory=seed(tmp_path);prepared=preview(executor,memory);result=execute(executor,prepared)
    writer=FilesystemInformationWrites(backend);writer.compact(executor.child_id('intent','information'))
    backend.delete_request('one','human','Remove',1,'delete');backend.approve_delete('one','delete')
    before=fingerprints(tmp_path)
    assert execute(executor,prepared)==result and fingerprints(tmp_path)==before and backend.get('one') is None


def test_no_project_receipt_copy_and_replay_are_portable(tmp_path):
    source,destination=tmp_path/'source',tmp_path/'clone'
    backend,executor,memory=seed(source);prepared=preview(executor,memory);result=execute(executor,prepared)
    assert copy_core(source,destination)['status']=='COPIED'
    other=RoutingExecutor(FilesystemBackend(destination/'memory/persistent',destination/'memory/history'))
    assert execute(other,prepared)==result and other.backend.get('one')==backend.get('one')


def test_unknown_journal_blocks_before_any_no_project_child(tmp_path):
    backend,executor,memory=seed(tmp_path);prepared=preview(executor,memory)
    path=backend.history_root/'operations/unknown/one.json';path.parent.mkdir(parents=True);path.write_text('{}')
    with pytest.raises(OperationConflict):execute(executor,prepared)
    assert executor.journal.read('intent') is None and backend.get('one') is None


def test_cli_preview_information_bootstraps_only_on_execution(tmp_path,capsys):
    root=tmp_path/'missing';_,_,memory=seed(tmp_path/'fixture')
    memory_path=tmp_path/'input.json';context_path=tmp_path/'context.json';plan_path=tmp_path/'plan.json'
    memory_path.write_text(json.dumps(asdict(memory)));context_path.write_text(json.dumps(asdict(RoutingContext(query_scope=SCOPE))))
    before=fingerprints(tmp_path)
    assert main(['--root',str(root),'preview-information','--memory',str(memory_path),'--context',str(context_path)])==0
    prepared=json.loads(capsys.readouterr().out);assert prepared['format_version']==5 and fingerprints(tmp_path)==before
    plan_path.write_text(json.dumps(prepared))
    assert main(['--root',str(root),'execute','--plan',str(plan_path),'--intent-id','intent','--actor','human','--timestamp',STAMP])==0
    assert json.loads(capsys.readouterr().out)['project'] is None and not list((root/'memory/persistent/threads').glob('*.md'))


def test_assessment_proposes_no_project_preview_explicitly(tmp_path):
    _,executor,memory=seed(tmp_path)
    result=executor.assess(memory,RoutingContext(query_scope=SCOPE))
    assert result['status']=='PREVIEW_REQUIRED' and result['next_step']=='PREVIEW_INFORMATION'


def test_source_changed_after_preview_does_not_reserve_parent(tmp_path):
    backend,executor,memory=seed(tmp_path)
    execute(executor,preview(executor,memory))
    current=backend.get('one')
    prepared=preview(executor,replace(current,content='Correction'),update_target=TargetRevision('one',1))
    backend._path('one').write_text(backend._serialize_checked(replace(current,content='Other edit')))
    with pytest.raises(OperationConflict):execute(executor,prepared,'update')
    assert executor.journal.read('update') is None and backend.get('one').content=='Other edit'


@pytest.mark.parametrize('field',['project','projection_digest','lifecycle'])
def test_corrupt_no_dossier_receipt_blocks_replay(tmp_path,field):
    backend,executor,memory=seed(tmp_path);prepared=preview(executor,memory)
    execute(executor,prepared)
    record=executor.journal.read('intent')
    record['result'][field]={'project':{'id':'fake','revision':1},
                             'projection_digest':'0'*64,'lifecycle':{'availability':'CONFIRMED','trigger_id':None}}[field]
    executor.journal.path('intent').write_text(json.dumps(record))
    before=backend.get('one')
    with pytest.raises(OperationConflict):execute(executor,prepared)
    assert backend.get('one')==before and not check_readiness(tmp_path)['ready']


def test_two_processes_replay_same_no_project_intent_once(tmp_path):
    backend,executor,memory=seed(tmp_path);memory=replace(memory,temporal={'resume_at':DUE})
    prepared=preview(executor,memory);path=tmp_path/'plan.json';path.write_text(json.dumps(prepared))
    script='''
import sys,json
from pathlib import Path
from core.backend.filesystem import FilesystemBackend
from core.routing.execution import RoutingExecutor
root=Path(sys.argv[1]);executor=RoutingExecutor(FilesystemBackend(root/'memory/persistent',root/'memory/history'))
print(json.dumps(executor.execute(json.loads(Path(sys.argv[2]).read_text()),intent_id='intent',actor='human',timestamp='2026-10-03T01:00:00Z'),sort_keys=True))
'''
    children=[subprocess.Popen([sys.executable,'-B','-c',script,str(tmp_path),str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)]
    replies=[child.communicate(timeout=15) for child in children]
    assert all(child.returncode==0 for child in children),replies
    assert json.loads(replies[0][0])==json.loads(replies[1][0])
    assert backend.get('one').revision==1 and check_readiness(tmp_path)['ready']
    triggers=LifecycleTriggers(backend).journal
    assert len(triggers.ids())==1 and triggers.read(triggers.ids()[0])['status']=='SCHEDULED'
