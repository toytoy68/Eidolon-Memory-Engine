"""Explicit project creation uses the existing durable children and owner guard."""
from dataclasses import asdict, replace
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.information.writes import FilesystemInformationWrites
from core.lifecycle.service import LifecycleTriggers
from core.migration.inventory import inventory
from core.operations.errors import OperationConflict
from core.operations.readiness import check_readiness, recover_all
from core.routing.execution import RoutingExecutor
from core.routing.policy import RoutingContext, TargetRevision
from core.threads.models import Thread, ThreadStatus
from core.threads.serialization import thread_to_dict
from core.threads.service import ThreadService
from tools.vm_acceptance import hashes
from tests.test_routing_execution import STAMP, execute, seed

DUE = '2026-10-03T08:00:00Z'


def fixture(root):
    backend = FilesystemBackend(root / 'memory/persistent', root / 'memory/history')
    executor = RoutingExecutor(backend)
    memory = Memory('first', content='Measure 200 W', metadata={
        'type': 'OBSERVATION', 'epistemic_status': 'CONFIRMED',
        'qualification': {'version': '0.1', 'nature': 'TECHNICAL', 'qualified_by': 'human'},
        'context': {'project_id': 'project', 'scope': {'goal': 'efficiency'}}},
        temporal={'observed_at': STAMP, 'resume_at': DUE}, provenance={'source': 'measurement'})
    project = Thread('project', 'Cooling project', 'Measure efficiency',
                     created_at=STAMP, updated_at=STAMP, provenance={'requested_by': 'human'})
    context = RoutingContext(query_scope={'goal': 'efficiency'}, selected_project='project')
    return backend, executor, memory, project, context


def prepared_at(root):
    backend, executor, memory, project, context = fixture(root)
    return backend, executor, executor.preview_new_project(memory, context, project=project)


def test_preview_is_read_only_and_complete_new_project_route_replays_once(tmp_path):
    backend, executor, memory, project, context = fixture(tmp_path)
    before = hashes(tmp_path)
    prepared = executor.preview_new_project(memory, context, project=project)
    assert hashes(tmp_path) == before and not executor.storage.threads_root.exists()
    assert prepared['format_version'] == 3 and prepared['project_before'] is None
    result = execute(executor, prepared)
    assert result['project'] == dict(id='project', revision=1)
    assert result['information'] == dict(id='first', revision=1)
    assert backend.get('first').metadata['epistemic_status'] == 'CONFIRMED'
    assert backend.get('first').metadata['availability'] == 'INTERMEDIATE'
    actual = executor.storage.get('project')
    assert actual == replace(project, relations=[dict(type='CONCERNS', target_id='first')])
    assert executor.dossiers.status('project')['status'] == 'CURRENT'
    assert check_readiness(tmp_path)['ready']
    assert inventory(tmp_path)['categories']['routing_executions'] == {'routing_execution_v3': 1}
    receipt = executor.journal.read('intent')
    assert 'command' not in receipt and 'Cooling project' not in json.dumps(receipt)
    stable = hashes(tmp_path)
    assert execute(executor, prepared) == result and hashes(tmp_path) == stable
    trigger_id = result['lifecycle']['trigger_id']
    assert LifecycleTriggers(backend).run_due(at=DUE, query_scope={'goal': 'efficiency'})[trigger_id]['status'] == 'COMPLETED'
    assert backend.get('first').revision == 2


def test_update_existing_information_into_explicit_new_project(tmp_path):
    backend, executor, memory, project, context = fixture(tmp_path)
    writes = FilesystemInformationWrites(backend)
    writes.create(memory, operation_id='initial', event_id='initial-event', actor='human', timestamp=STAMP)
    writes.rebuild_reservation_index()
    context = replace(context, update_target=TargetRevision('first', 1))
    prepared = executor.preview_new_project(replace(memory, content='Corrected 210 W'), context, project=project)
    result = execute(executor, prepared)
    assert backend.get('first').revision == 2 and backend.get('first').content == 'Corrected 210 W'
    assert result['project']['revision'] == 1 and result['information']['revision'] == 2
    assert executor.dossiers.status('project')['status'] == 'CURRENT'


@pytest.mark.parametrize('boundary', ['before_information', 'after_information', 'after_project', 'after_projection', 'after_trigger'])
def test_interrupted_creation_reserves_identity_and_recovers_globally(tmp_path, monkeypatch, boundary):
    backend, executor, prepared = prepared_at(tmp_path)
    def stop(stage):
        if stage == boundary: raise RuntimeError('stop')
    with monkeypatch.context() as patch:
        patch.setattr(executor, '_checkpoint', stop)
        with pytest.raises(RuntimeError): execute(executor, prepared)
    assert not check_readiness(tmp_path)['ready']
    with pytest.raises(OperationConflict, match='routing intention'):
        ThreadService.for_backend(backend).create_linked(
            Thread('project', 'Other', 'Other', created_at=STAMP, updated_at=STAMP),
            'foreign', operation_id='foreign-create', event_id='foreign-event')
    assert recover_all(tmp_path)['readiness']['ready']
    assert execute(executor, prepared)['project']['revision'] == 1
    assert executor.dossiers.status('project')['status'] == 'CURRENT'
    assert len(LifecycleTriggers(backend).journal.ids()) == 1


@pytest.mark.parametrize('field,value', [('thread_id', 'other'), ('revision', 2),
    ('status', ThreadStatus.VALIDATED), ('relations', [{'type': 'CONCERNS', 'target_id': 'foreign'}])])
def test_new_project_template_must_be_explicit_and_fresh(tmp_path, field, value):
    backend, executor, memory, project, context = fixture(tmp_path)
    before = hashes(tmp_path)
    with pytest.raises(OperationConflict):
        executor.preview_new_project(memory, context, project=replace(project, **{field: value}))
    assert hashes(tmp_path) == before and backend.get('first') is None


def test_stale_absence_refused_before_information_and_foreign_project_unchanged(tmp_path):
    backend, executor, prepared = prepared_at(tmp_path)
    service = ThreadService.for_backend(backend)
    foreign = Thread('project', 'Another project', 'Unrelated', created_at=STAMP, updated_at=STAMP)
    service.storage.create(foreign)
    with pytest.raises(OperationConflict, match='stale'):
        execute(executor, prepared)
    assert backend.get('first') is None and service.get('project') == foreign
    assert executor.journal.read('intent') is None


def test_previous_deleted_identity_is_not_reused_for_new_project(tmp_path):
    backend, executor, memory, project, context = fixture(tmp_path)
    backend.store(Memory('older'))
    service = ThreadService.for_backend(backend)
    service.create_linked(project, 'older', operation_id='previous-project', event_id='previous-event')
    service.delete('project', previous_revision=1, operation_id='delete-project')
    prepared = executor.preview_new_project(memory, context, project=project)
    with pytest.raises(OperationConflict):
        execute(executor, prepared)
    assert backend.get('first') is None and executor.journal.read('intent') is None


def test_foreign_matching_project_after_intent_is_not_adopted_without_child_proof(tmp_path, monkeypatch):
    backend, executor, prepared = prepared_at(tmp_path)
    with monkeypatch.context() as patch:
        patch.setattr(executor, '_checkpoint', lambda stage: (_ for _ in ()).throw(RuntimeError()) if stage == 'after_information' else None)
        with pytest.raises(RuntimeError): execute(executor, prepared)
    template = executor.storage._deserialize(prepared['project_create'])
    forged = replace(template, relations=[{'type': 'CONCERNS', 'target_id': 'first'}])
    executor.storage._path('project').write_text(executor.storage._serialize_checked(forged))
    assert not recover_all(tmp_path)['readiness']['ready']
    with pytest.raises(OperationConflict, match='project diverged'):
        execute(executor, prepared)


def test_replay_after_project_and_information_deletion_does_not_resurrect(tmp_path):
    backend, executor, prepared = prepared_at(tmp_path)
    result = execute(executor, prepared)
    service = ThreadService.for_backend(backend)
    service.delete('project', previous_revision=1, operation_id='delete-project')
    FilesystemInformationWrites(backend).compact(executor.child_id('intent', 'information'))
    backend.delete_request('first', 'human', 'remove', 1, 'delete-first')
    backend.approve_delete('first', 'delete-first')
    stable = hashes(tmp_path)
    assert execute(executor, prepared) == result and hashes(tmp_path) == stable
    assert backend.get('first') is None and service.get('project') is None


def test_changed_new_project_command_with_same_intent_is_refused(tmp_path):
    backend, executor, prepared = prepared_at(tmp_path)
    execute(executor, prepared)
    changed = dict(prepared, project_create=prepared['project_create'].replace('Cooling project', 'Different'))
    with pytest.raises(OperationConflict, match='different plan'):
        execute(executor, changed)


def crash(root, boundary):
    backend, executor, prepared = prepared_at(Path(root))
    def stop(stage):
        if stage == boundary: os._exit(74)
    executor._checkpoint = stop
    execute(executor, prepared)


@pytest.mark.parametrize('boundary', ['after_information', 'after_project', 'after_trigger'])
def test_process_exit_then_global_recovery_creates_each_child_once(tmp_path, boundary):
    _, _, prepared = prepared_at(tmp_path)
    child = multiprocessing.get_context('spawn').Process(target=crash, args=(str(tmp_path), boundary))
    child.start(); child.join(15)
    try: assert child.exitcode == 74
    finally:
        if child.is_alive(): child.terminate(); child.join()
    assert recover_all(tmp_path)['readiness']['ready']
    backend = FilesystemBackend(tmp_path / 'memory/persistent', tmp_path / 'memory/history')
    executor = RoutingExecutor(backend)
    assert execute(executor, prepared)['project']['revision'] == 1
    assert len(list((backend.history_root / 'events/thread-create-v1').glob('*.md'))) == 1
    assert len(list((backend.history_root / 'events/information-write-v1').glob('*.md'))) == 1


def competitor(root, memory_id, ready, start):
    backend, executor, memory, project, context = fixture(Path(root))
    prepared = executor.preview_new_project(replace(memory, information_id=memory_id), context, project=project)
    ready.set()
    if not start.wait(10): raise RuntimeError('timeout')
    try:
        execute(executor, prepared, memory_id)
        result = 'COMMITTED'
    except OperationConflict:
        result = 'CONFLICT'
    (Path(root) / (memory_id + '.result')).write_text(result)


def test_two_creators_for_same_new_project_have_one_winner_and_no_losing_information(tmp_path):
    backend, _, _, _, _ = fixture(tmp_path)
    ctx = multiprocessing.get_context('spawn')
    start = ctx.Event(); ready = [ctx.Event(), ctx.Event()]
    children = [ctx.Process(target=competitor, args=(str(tmp_path), name, ready[i], start)) for i, name in enumerate(['one', 'two'])]
    try:
        for child in children: child.start()
        assert all(event.wait(10) for event in ready)
        start.set()
        for child in children:
            child.join(15); assert child.exitcode == 0
    finally:
        for child in children:
            if child.is_alive(): child.terminate(); child.join()
    results = {name: (tmp_path / (name + '.result')).read_text() for name in ['one', 'two']}
    assert sorted(results.values()) == ['COMMITTED', 'CONFLICT']
    assert sum(backend.get(name) is not None for name in results) == 1
    assert check_readiness(tmp_path)['ready']


def test_existing_project_format_two_with_reservation_index(tmp_path):
    backend, executor, memory = seed(tmp_path)
    FilesystemInformationWrites(backend).rebuild_reservation_index()
    prepared = executor.preview(memory, RoutingContext(query_scope={'goal': 'efficiency'}), project_revision=1, include_lifecycle=True)
    assert execute(executor, prepared)['project']['revision'] == 2


@pytest.mark.parametrize('after_event', [False, True])
def test_failure_inside_project_creation_child_resumes_without_duplicate(tmp_path, monkeypatch, after_event):
    from core.events.filesystem import FilesystemEventRepository
    backend, executor, prepared = prepared_at(tmp_path)
    original = FilesystemEventRepository.save
    def stop(repository, event):
        if event.thread_id == 'project':
            if after_event: original(repository, event)
            raise RuntimeError('child interrupted')
        return original(repository, event)
    with monkeypatch.context() as patch:
        patch.setattr(FilesystemEventRepository, 'save', stop)
        with pytest.raises(RuntimeError): execute(executor, prepared)
    assert executor.storage.get('project').revision == 1
    assert not check_readiness(tmp_path)['ready']
    assert recover_all(tmp_path)['readiness']['ready']
    assert execute(executor, prepared)['project']['revision'] == 1
    assert len(list((backend.history_root / 'events/thread-create-v1').glob('*.md'))) == 1


def test_cli_preview_new_project_on_empty_root_then_execute(tmp_path):
    _, _, memory, project, context = fixture(tmp_path / 'input')
    for name, value in [('memory', asdict(memory)), ('project', thread_to_dict(project)), ('context', asdict(context))]:
        (tmp_path / (name + '.json')).write_text(json.dumps(value))
    root = tmp_path / 'new-engine'
    base = [sys.executable, '-B', '-m', 'core.routing.execution_cli', '--root', str(root)]
    result = subprocess.run(base + ['preview', '--memory', str(tmp_path/'memory.json'), '--context', str(tmp_path/'context.json'), '--new-project', str(tmp_path/'project.json')], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not root.exists()
    plan_path = tmp_path / 'plan.json'; plan_path.write_text(result.stdout)
    result = subprocess.run(base + ['execute', '--plan', str(plan_path), '--intent-id', 'cli-new', '--actor', 'human', '--timestamp', STAMP], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)['project']['revision'] == 1 and check_readiness(root)['ready']
