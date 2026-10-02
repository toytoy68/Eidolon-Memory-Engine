"""Clients handle NONE/REVIEW before choosing an explicit executable journey."""
from copy import deepcopy
from dataclasses import asdict, replace
import json

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.routing.execution import RoutingExecutor
from core.routing.execution_cli import main
from core.routing.outcomes import assess
from core.routing.policy import RoutingContext, TargetRevision, plan
from tests.test_memory_policy import from_case
from tests.test_migration_converter import fingerprints
from tests.test_routing_execution import seed, preview, execute


def qualified(nature='TECHNICAL', **context):
    return Memory('input',content='Claim',metadata={
        'qualification':{'version':'0.1','nature':nature,'qualified_by':'human'},
        'epistemic_status':'UNVERIFIED','context':context},
        provenance={'source':'human','author_role':'ADMIN'})


@pytest.mark.parametrize('case_id',['admin-philosophical-exploration','robot-passing-cat'])
def test_none_is_a_finished_read_only_outcome(case_id):
    memory=from_case(case_id);context=RoutingContext();before=deepcopy(memory)
    result=assess(memory,context)
    assert result['status']=='NO_ACTION' and result['next_step']=='DO_NOT_PERSIST'
    assert result['policy']==json.loads(json.dumps(asdict(plan(memory,context))))
    assert result['writes_performed'] is False and result['review_reasons']==[]
    assert memory==before
    assert result['policy']['automatic_delete'] is False
    assert assess(memory,context)==result


@pytest.mark.parametrize('memory,context,reason',[
 (Memory('input',content='Unqualified'),RoutingContext(),'explicit_qualification_required_no_inference_from_text'),
 (qualified('SPATIAL_LAYOUT'),RoutingContext(),'layout_requires_declared_place'),
 (qualified(project_id='one'),RoutingContext(candidate_projects=('two','three')),'ambiguous_project_no_automatic_merge'),
 (replace(qualified(project_id='one'),temporal={'resume_at':'not-a-date'}),RoutingContext(),'resume_at_requires_valid_explicit_timezone'),
 (qualified('OBSTACLE',project_id='one'),RoutingContext(removal_observed=True,update_target=TargetRevision('input',1),evidence_refs=('declared',)),'removal_evidence_requires_review'),
 (qualified(project_id='one',scope={'place':'lab'}),RoutingContext(query_scope={'place':'lab'},unresolved_conflict=True),'same_context_conflict_requires_evidence_no_automatic_winner'),
])
def test_review_does_not_silently_accept_partial_store(memory,context,reason):
    result=assess(memory,context)
    assert result['status']=='REVIEW_REQUIRED' and result['next_step']=='RESOLVE_REVIEW'
    assert reason in result['review_reasons'] and result['writes_performed'] is False
    assert result['policy']==json.loads(json.dumps(asdict(plan(memory,context))))


@pytest.mark.parametrize('existing,next_step',[(None,'RESOLVE_PROJECT'),('one','PREVIEW_EXISTING_PROJECT')])
def test_project_candidate_still_requires_preview_and_explicit_execution(existing,next_step):
    result=assess(qualified(project_id='one'),RoutingContext(existing_dossier=existing))
    assert result['status']=='PREVIEW_REQUIRED' and result['next_step']==next_step
    assert result['writes_performed'] is False
    assert result['policy']['epistemic_status']=='UNVERIFIED'


@pytest.mark.parametrize('context',[{'place_id':'lab'},{'topic_id':'efficiency'},{}])
def test_other_routes_are_identified_without_claiming_execution(context):
    result=assess(qualified(**context),RoutingContext())
    assert result['status']=='CAPABILITY_REQUIRED' and result['next_step']=='UNSUPPORTED_ROUTE'
    assert result['writes_performed'] is False


def test_already_stored_with_requested_association_is_not_silent_noop():
    memory=qualified(project_id='one')
    result=assess(memory,RoutingContext(already_stored=True,existing_dossier='one'))
    assert result['policy']['persistence']=='NONE'
    assert result['status']=='REVIEW_REQUIRED'
    assert 'association_requires_explicit_command' in result['review_reasons']


def test_already_stored_without_association_is_noop_and_preserves_deadline():
    memory=replace(qualified(),temporal={'resume_at':'2026-10-04T12:00:00Z'})
    result=assess(memory,RoutingContext(already_stored=True))
    assert result['status']=='NO_ACTION' and result['policy']['proposed_trigger'] is None
    assert memory.temporal['resume_at']=='2026-10-04T12:00:00Z'


def test_client_can_resolve_review_explicitly_and_use_existing_journey(tmp_path):
    backend,executor,target=seed(tmp_path)
    unqualified=replace(target,metadata={})
    before=fingerprints(tmp_path)
    assert executor.assess(unqualified,RoutingContext())['status']=='REVIEW_REQUIRED'
    assert fingerprints(tmp_path)==before and backend.get(target.information_id) is None
    assessment=executor.assess(target,RoutingContext(existing_dossier='project'))
    assert assessment['next_step']=='PREVIEW_EXISTING_PROJECT' and fingerprints(tmp_path)==before
    prepared=preview(executor,target);result=execute(executor,prepared)
    assert backend.get(target.information_id).revision==result['information']['revision']==1
    bundle=executor.recall('measure',query_scope={'goal':'efficiency'},max_chars=4000)
    assert any(item.information_id==target.information_id and item.needs_review for item in bundle.items)


def test_outcome_values_have_no_mutable_aliases():
    memory=qualified(project_id='one');context=RoutingContext(query_scope={'nested':{'room':'lab'}})
    before=deepcopy((memory,context))
    result=assess(memory,context)
    result['policy']['source_provenance']['source']='different'
    result['policy']['reasons'].append('different')
    assert (memory,context)==before
    assert assess(memory,context)['policy']['source_provenance']['source']=='human'


@pytest.mark.parametrize('state',['absent','failed','pending-delete','corrupt-thread'])
def test_assessment_does_not_initialize_or_recover_engine_state(tmp_path,state):
    root=tmp_path/'engine'
    backend=FilesystemBackend.__new__(FilesystemBackend)
    backend.persistent_root=root/'memory/persistent';backend.history_root=root/'memory/history'
    backend.pending_delete_root=backend.history_root/'pending-delete'
    if state!='absent':
        path={'failed':'history/operations/information-write-v1/fail.json',
              'pending-delete':'history/pending-delete/input.json',
              'corrupt-thread':'persistent/threads/one.md'}[state]
        entry=root/'memory'/path;entry.parent.mkdir(parents=True);entry.write_text('invalid')
    before=fingerprints(tmp_path)
    result=RoutingExecutor(backend).assess(from_case('robot-passing-cat'),RoutingContext())
    assert result['status']=='NO_ACTION' and fingerprints(tmp_path)==before
    # This is an assessment, not an assertion of engine readiness.
    assert result['execution_validated'] is False


@pytest.mark.parametrize('revision',[0,True,'1'])
def test_invalid_memory_is_rejected_before_any_outcome(revision):
    from core.backend.errors import InvalidMemory
    with pytest.raises(InvalidMemory):assess(replace(qualified(),revision=revision),RoutingContext())


def test_cli_assess_is_read_only_and_review_is_a_valid_result(tmp_path,capsys):
    root=tmp_path/'missing';memory_path=tmp_path/'input.json';context_path=tmp_path/'context.json'
    memory_path.write_text(json.dumps(asdict(Memory('input',content='Not qualified'))))
    context_path.write_text('{}');before=fingerprints(tmp_path)
    code=main(['--root',str(root),'assess','--memory',str(memory_path),'--context',str(context_path)])
    assert code==0 and json.loads(capsys.readouterr().out)['status']=='REVIEW_REQUIRED'
    assert fingerprints(tmp_path)==before


def test_none_does_not_delete_existing_information(tmp_path):
    backend,executor,_=seed(tmp_path)
    proposed=replace(qualified('REFLECTION'),information_id='initial')
    before=fingerprints(tmp_path)
    result=executor.assess(proposed,RoutingContext())
    assert result['status']=='NO_ACTION' and fingerprints(tmp_path)==before
    assert backend.get('initial').content=='first source'


def test_assessment_is_not_an_executable_plan(tmp_path):
    from core.operations.errors import OperationConflict
    backend,executor,target=seed(tmp_path)
    outcome=executor.assess(target,RoutingContext(existing_dossier='project'))
    before=backend.get('initial');thread_before=executor.storage.get('project')
    with pytest.raises(OperationConflict):execute(executor,outcome)
    assert backend.get(target.information_id) is None and backend.get('initial')==before
    assert executor.storage.get('project')==thread_before and executor.journal.read('intent') is None


def test_context_without_explicit_dossier_does_not_assume_project_is_new(tmp_path):
    _,executor,target=seed(tmp_path)
    before=fingerprints(tmp_path)
    result=executor.assess(target,RoutingContext())
    assert result['status']=='PREVIEW_REQUIRED' and result['next_step']=='RESOLVE_PROJECT'
    assert fingerprints(tmp_path)==before and executor.storage.get('project') is not None
