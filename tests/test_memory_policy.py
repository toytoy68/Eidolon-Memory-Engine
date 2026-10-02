from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from core.backend.models import Memory
from core.routing.policy import RoutingContext, TargetRevision, applicability, plan


FIXTURE = json.loads((Path(__file__).parent / 'fixtures/memory-policy-v0.1.json').read_text())
CASES = {item['id']: item for item in FIXTURE['cases']}


def from_case(case_id, given=None):
    """Translate the compact acceptance example to explicitly annotated Memory."""
    source = given if given is not None else CASES[case_id]['given']
    context = {key: source[key] for key in ('project_id', 'place_id', 'topic_id') if key in source}
    metadata = {key: source[key] for key in ('type', 'epistemic_status') if key in source}
    if 'nature' in source:
        metadata['qualification'] = {'version': '0.1', 'nature': source['nature'],
                                      'horizon': 'UNKNOWN', 'qualified_by': 'acceptance-fixture'}
    metadata['context'] = context
    return Memory(case_id, content=source.get('content'), metadata=metadata,
                  provenance={key: source[key] for key in ('source', 'author_role') if key in source},
                  temporal={key: source[key] for key in ('observed_at', 'valid_until', 'resume_at') if key in source})


@pytest.mark.parametrize('case_id', [
    'admin-technical-hypothesis', 'admin-philosophical-exploration',
    'explicit-reflection-to-revisit', 'robot-corridor-layout', 'robot-passing-cat',
    'cat-observation-for-tracking-task', 'ambiguous-project-association',
])
def test_reference_routing_examples(case_id):
    case = CASES[case_id]
    given = case['given']
    memory = from_case(case_id)
    before = deepcopy(memory)
    context = RoutingContext(explicit_memory_request=given.get('explicit_memory_request', False),
                             navigation_active=given.get('navigation_active', False),
                             tracking_task=given.get('tracking_task', False),
                             significant_event=given.get('significant_event', False),
                             candidate_projects=tuple(given.get('candidate_projects', [])))
    result = plan(memory, context)
    for field in ('persistence', 'availability', 'dossier', 'epistemic_status', 'horizon'):
        if field in case['expected']:
            assert getattr(result, field) == case['expected'][field], (case_id, field)
    assert memory == before
    assert result.reasons
    assert result.automatic_delete is False
    assert result.source_revision == memory.revision
    assert result.source_provenance == memory.provenance
    assert result.source_temporal == memory.temporal


def test_fork_bypassed_keeps_obstacle_and_recheck_separate_from_action():
    given = CASES['fork-bypassed']['given']
    obstacle = from_case('obstacle', given['items'][0])
    action = from_case('action', given['items'][1])
    first = plan(obstacle, RoutingContext(navigation_active=True))
    second = plan(action, RoutingContext(navigation_active=True))
    assert first.persistence == 'STORE'
    assert first.availability == 'HIGH'
    assert first.after_task_availability == 'INTERMEDIATE'
    assert first.recheck_before_reuse is True
    assert first.current_obstacle is not False
    assert second.current_obstacle is not False
    assert second.update_target is None


def test_removal_requires_target_revision_and_evidence():
    case = CASES['fork-removal-observed']['given']
    memory = Memory(case['known_obstacle_id'], revision=case['expected_revision'],
                    metadata={'qualification': {'version': '0.1', 'nature': 'OBSTACLE',
                                                 'qualified_by': 'acceptance-fixture'}},
                    provenance={'source': case['observation_source']})
    target = TargetRevision(case['known_obstacle_id'], case['expected_revision'])
    context = RoutingContext(removal_observed=True, update_target=target,
                             evidence_refs=('observation-removal-1',))
    result = plan(memory, context)
    assert result.persistence == 'UPDATE'
    assert result.update_target == target
    assert result.current_obstacle is False
    assert result.evidence_refs == ('observation-removal-1',)
    assert result.automatic_delete is False
    assert plan(memory, replace(context, evidence_refs=())).persistence == 'REVIEW'
    assert plan(memory, replace(context, update_target=None)).persistence == 'REVIEW'


def test_conditional_claims_can_both_remain_confirmed():
    case = CASES['conditional-gpu-recommendations']
    matches, outside = [], []
    for claim in case['given']['claims']:
        memory = Memory(claim['id'], content=claim['power_w'],
                        metadata={'epistemic_status': claim['epistemic_status'],
                                  'context': {'scope': {'conditions': claim['conditions']}}})
        result = applicability(memory, {'conditions': case['given']['query_context']})
        if result == 'MATCH':
            matches.append(memory.information_id)
        if result == 'OUT_OF_SCOPE':
            outside.append(memory.information_id)
        assert memory.metadata['epistemic_status'] == 'CONFIRMED'
    assert matches == case['expected']['matching_ids']
    assert outside == case['expected']['out_of_scope_ids']


def test_missing_scope_or_query_condition_never_means_universal():
    case = CASES['missing-context-is-not-universal']['given']
    memory = Memory('conditional', metadata={'context': {'scope': {'conditions': case['conditions']}}})
    assert applicability(memory, case['query_context']) == 'UNKNOWN'
    assert applicability(Memory('without-scope'), {'subject_id': 'anything'}) == 'UNKNOWN'
    assert applicability(memory, {'conditions': {'goal': 'other'}}) == 'OUT_OF_SCOPE'


def test_same_context_conflict_has_no_automatic_winner():
    given = CASES['same-context-unresolved-conflict']['given']
    scope = {'subject_id': given['subject_id'], 'place_id': given['place_id']}
    for count in given['claims']:
        memory = Memory(f'claim-{count}', content=count, metadata={
            'epistemic_status': 'CONFLICTED', 'context': {'scope': scope}})
        result = plan(memory, RoutingContext(query_scope=scope, unresolved_conflict=True))
        assert result.applicability == 'UNRESOLVED'
        assert result.automatic_winner is None
        assert result.epistemic_status == 'CONFLICTED'


def test_expired_does_not_mean_refuted_or_deleted():
    case_id = 'expired-but-historically-true'
    given = CASES[case_id]['given']
    memory = from_case(case_id)
    result = plan(memory, RoutingContext(at=given['query_at'], already_stored=True))
    assert result.applicability == 'EXPIRED'
    assert result.epistemic_status == 'CONFIRMED'
    assert result.automatic_delete is False
    assert result.persistence != 'STORE'


def test_scheduled_restart_proposes_stable_trigger_but_does_not_execute_it():
    case_id = 'scheduled-project-restart'
    memory = from_case(case_id)
    context = RoutingContext(at='2026-10-04T10:00:00Z')
    result = plan(memory, context)
    assert result.persistence == 'STORE'
    assert result.availability == 'INTERMEDIATE'
    assert result.dossier == 'CREATE_OR_LINK'
    assert result.proposed_trigger['at'] == memory.temporal['resume_at']
    assert result.proposed_trigger['kind'] == 'REACTIVATE'
    assert result.proposed_trigger == plan(memory, context).proposed_trigger
    # Durability and activation_count_after_replay belong to T-046, not this planner.


def test_source_role_does_not_promote_truth_and_plan_has_no_aliases():
    memory = from_case('admin-technical-hypothesis')
    result = plan(memory, RoutingContext())
    alternate = replace(memory, provenance={'author_role': 'VISITOR'})
    other = plan(alternate, RoutingContext())
    assert result.epistemic_status == other.epistemic_status == 'UNVERIFIED'
    assert result.persistence == other.persistence
    result.source_provenance['author_role'] = 'changed'
    assert memory.provenance['author_role'] == 'ADMIN'


def test_unqualified_input_requires_review_without_guessing_from_words():
    memory = Memory('unknown', content='Projet robot chat dans le couloir', provenance={'author_role': 'ADMIN'})
    result = plan(memory, RoutingContext())
    assert result.persistence == 'REVIEW'
    assert result.nature is None
    assert result.epistemic_status is None
    assert result.dossier == 'NONE'


def test_planner_cli_is_read_only_and_explains_each_dimension(tmp_path):
    from dataclasses import asdict
    import subprocess
    import sys
    from tools.vm_acceptance import hashes
    source = tmp_path / 'memory.json'
    context = tmp_path / 'context.json'
    source.write_text(json.dumps(asdict(from_case('robot-corridor-layout'))))
    context.write_text(json.dumps({'navigation_active': True}))
    before = hashes(tmp_path)
    result = subprocess.run([sys.executable, '-B', '-m', 'core.routing.cli', '--memory', str(source),
                             '--context', str(context)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output['horizon'] == 'LONG_TERM'
    assert output['persistence'] == 'STORE'
    assert output['epistemic_status'] == 'UNVERIFIED'
    assert output['reasons']
    assert output['source_id'] == 'robot-corridor-layout'
    assert hashes(tmp_path) == before


def test_cold_memory_keeps_project_pointer_and_can_be_planned_for_update():
    memory = from_case('admin-technical-hypothesis')
    memory.metadata['qualification']['horizon'] = 'LONG_TERM'
    context = RoutingContext(update_target=TargetRevision(memory.information_id, memory.revision),
                             existing_dossier='project-cooling')
    result = plan(memory, context)
    assert result.persistence == 'UPDATE'
    assert result.update_target.revision == 1
    assert result.availability == 'LOW'
    assert result.dossier == 'LINK'
    assert result.dossier_id == 'project-cooling'
    assert result.dossier_subject == {'kind': 'project', 'id': 'cooling'}


def test_known_context_mismatch_wins_over_another_missing_condition():
    memory = Memory('scoped', metadata={'context': {'scope': {
        'place_id': 'corridor', 'conditions': {'goal': 'efficiency'}}}})
    assert applicability(memory, {'conditions': {'goal': 'performance'}}) == 'OUT_OF_SCOPE'


def test_unresolved_conflict_elsewhere_is_not_misreported_in_query_scope():
    memory = Memory('conflict', metadata={'context': {'scope': {'place_id': 'elsewhere'}}})
    assert applicability(memory, {'place_id': 'here'}, unresolved_conflict=True) == 'OUT_OF_SCOPE'
