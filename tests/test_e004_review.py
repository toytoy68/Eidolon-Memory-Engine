"""Regressions reproduced from Claude's E-004 review (2026-10-02)."""
from dataclasses import asdict
import json

import pytest

from core.backend.models import Memory
from core.dossiers.projects import BEGIN, END, ProjectDossiers
from core.operations.errors import OperationConflict
from core.routing.policy import RoutingContext, TargetRevision, plan
from core.threads.models import Thread, ThreadAction
from tests.test_routing_execution import seed, preview, execute
from tests.test_migration_converter import fingerprints


def qualified(nature='OBSTACLE', **kwargs):
    return Memory('obstacle', metadata={'qualification': {
        'version': '0.1', 'nature': nature, 'qualified_by': 'human'}}, **kwargs)


def test_layout_update_without_place_stays_review_and_cannot_execute(tmp_path):
    backend, executor, memory = seed(tmp_path)
    backend.store(memory)
    prepared = preview(executor, memory, update_target=TargetRevision('second', 1))
    memory.metadata['qualification']['nature'] = 'SPATIAL_LAYOUT'
    context = RoutingContext(query_scope={'goal': 'efficiency'}, update_target=TargetRevision('second', 1))
    before = fingerprints(tmp_path)
    result = plan(memory, context)
    assert result.persistence == 'REVIEW'
    assert result.update_target is None
    with pytest.raises(OperationConflict):
        preview(executor, memory, update_target=context.update_target)
    assert fingerprints(tmp_path) == before
    # Even a plan matching its inputs must be rejected when it requires review.
    prepared['memory']['metadata']['qualification']['nature'] = 'SPATIAL_LAYOUT'
    prepared['policy'] = json.loads(json.dumps(asdict(result)))
    with pytest.raises(OperationConflict):
        execute(executor, prepared)
    assert not executor.journal.path('intent').exists()
    assert {k: v for k, v in fingerprints(tmp_path).items() if not k.endswith('.write.lock')} == {
        k: v for k, v in before.items() if not k.endswith('.write.lock')}


@pytest.mark.parametrize('separator', ['\n', '\r', '\r\n', '\u2028', '\u2029', '\x85', '\v', '\f'])
@pytest.mark.parametrize('field', ['DECISION', 'QUESTION', 'summary', 'title', 'action', 'metadata', 'keywords'])
def test_multiline_fields_cannot_forge_dossier_structure(separator, field):
    payload = f'Choix A{separator}## Actions{separator}- [DONE] `fake` : fini'
    memory = Memory('source', content=payload if field in {'DECISION', 'QUESTION', 'summary'} else 'Source',
                    metadata={'type': field, 'keywords': [payload] if field == 'keywords' else []})
    thread = Thread('project', payload if field == 'title' else 'Projet', 'Objectif',
                    actions=[ThreadAction('real', payload if field == 'action' else 'Mesurer',
                                          metadata={'note': payload} if field == 'metadata' else {})])
    generated = ProjectDossiers._generated('project', (thread, [memory], [], 'digest'))
    lines = generated.splitlines()
    assert lines.count('## Actions') == 1
    assert not any(line.startswith('- [DONE] `fake`') for line in lines)
    assert generated.count(BEGIN) == generated.count(END) == 1
    if field in {'DECISION', 'QUESTION', 'summary'}:
        assert '> ## Actions\n> - [DONE] `fake` : fini' in generated


@pytest.mark.parametrize('nature,target,refs', [
    ('TECHNICAL', TargetRevision('obstacle', 1), ('evidence',)),
    ('OBSTACLE', TargetRevision('other', 1), ('evidence',)),
    ('OBSTACLE', TargetRevision('obstacle', 7), ('evidence',)),
    ('OBSTACLE', TargetRevision('obstacle', 1), ('',)),
    ('OBSTACLE', TargetRevision('obstacle', 1), ('   ',)),
    ('OBSTACLE', TargetRevision('obstacle', 1), (42,)),
])
def test_removal_proposal_requires_coherent_obstacle_target_and_references(nature, target, refs):
    result = plan(qualified(nature), RoutingContext(removal_observed=True, update_target=target, evidence_refs=refs))
    assert result.persistence == 'REVIEW'
    assert result.current_obstacle is None
    assert result.update_target is None


def test_unqualified_removal_requires_review():
    result = plan(Memory('obstacle'), RoutingContext(removal_observed=True,
                  update_target=TargetRevision('obstacle', 1), evidence_refs=('evidence',)))
    assert result.persistence == 'REVIEW'


@pytest.mark.parametrize('resume_at', ['invalid', '2026-10-03T08:00:00', 123, '', False])
def test_invalid_declared_resume_time_requires_review(resume_at):
    result = plan(qualified(temporal={'resume_at': resume_at}), RoutingContext())
    assert result.persistence == 'REVIEW'
    assert result.proposed_trigger is None


@pytest.mark.parametrize('review', [False, True])
def test_non_persistent_plan_has_no_trigger(review):
    memory = qualified('SPATIAL_LAYOUT' if review else 'TECHNICAL', temporal={'resume_at': '2026-10-03T08:00:00Z'})
    result = plan(memory, RoutingContext(already_stored=not review))
    assert result.persistence == ('REVIEW' if review else 'NONE')
    assert result.proposed_trigger is None
