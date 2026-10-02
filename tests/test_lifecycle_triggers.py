"""Explicit time, canonical mutation and interrupted acknowledgement behavior."""
from dataclasses import replace
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.indexing.catalogue import InformationCatalogue
from core.information.writes import FilesystemInformationWrites
from core.lifecycle.service import AvailabilityService, LifecycleTriggers
from core.migration.converter import convert
from core.operations.errors import OperationConflict
from core.operations.readiness import check_readiness, recover_all
from core.retrieval.contextual import ContextualRecall
from tools.vm_acceptance import hashes

CREATED = '2026-10-02T03:00:00Z'
DUE = '2026-10-02T04:00:00Z'
LATER = '2026-10-02T06:00:00Z'
SCOPE = {'project_id': 'cooling'}


def seed(root):
    backend = FilesystemBackend(root / 'memory/persistent', root / 'memory/history')
    memory = Memory('pump', content='Private pump observation', metadata={
        'type': 'OBSERVATION', 'epistemic_status': 'CONFIRMED', 'retention': 'LONG_TERM',
        'availability': 'LOW', 'context': {'scope': SCOPE},
        'qualification': {'nature': 'TECHNICAL'}}, provenance={'source': 'human observation'},
        temporal={'observed_at': CREATED})
    backend.store(memory)
    return backend, LifecycleTriggers(backend), memory


def schedule(service, identity='wake', **changes):
    args = dict(revision=1, kind='REACTIVATE', due_at=DUE, trigger_id=identity,
                actor='human', created_at=CREATED)
    args.update(changes)
    return service.schedule('pump', **args)


def test_overdue_after_restart_runs_once_and_preserves_meaning(tmp_path):
    backend, service, memory = seed(tmp_path)
    original = schedule(service)
    assert check_readiness(tmp_path)['ready']
    assert service.run_due(at=CREATED, query_scope=SCOPE) == {}
    restarted = LifecycleTriggers(backend)
    result = restarted.run_due(at=LATER, query_scope=SCOPE)['wake']
    assert result['status'] == 'COMPLETED' and result['result']['reason'] == 'HIGH'
    current = backend.get('pump')
    assert current == replace(memory, revision=2, metadata=dict(memory.metadata, availability='HIGH'))
    stable = hashes(tmp_path)
    assert restarted.run_due(at=LATER, query_scope=SCOPE) == {}
    assert schedule(restarted) == result
    assert hashes(tmp_path) == stable
    assert original['source_sha256'] == result['source_sha256']
    assert 'Private pump observation' not in service.journal.path('wake').read_text()


@pytest.mark.parametrize('direct', [False, True])
def test_source_change_invalidates_deadline_without_overwriting_correction(tmp_path, direct):
    backend, service, memory = seed(tmp_path)
    schedule(service)
    if direct:
        path = backend._path('pump')
        path.write_text(path.read_text().replace('Private pump observation', 'Corrected observation'))
    else:
        backend.update('pump', replace(memory, content='Corrected observation'), 1)
    current = backend.get('pump')
    result = service.run_due(at=DUE, query_scope=SCOPE)['wake']
    assert result['status'] == 'STALE' and backend.get('pump') == current
    assert not (backend.history_root / 'operations/information-write-v1').exists()


def test_cancellation_replay_and_identity_are_stable(tmp_path):
    backend, service, memory = seed(tmp_path)
    schedule(service)
    cancelled = service.cancel('wake', actor='human', at=CREATED, reason='not needed')
    before = hashes(tmp_path)
    assert service.cancel('wake', actor='human', at=CREATED, reason='not needed') == cancelled
    assert schedule(service) == cancelled
    assert service.run_due(at=LATER) == {}
    assert hashes(tmp_path) == before and backend.get('pump') == memory
    with pytest.raises(OperationConflict):
        schedule(service, due_at=LATER)
    with pytest.raises(OperationConflict):
        service.cancel('wake', actor='human', at=CREATED, reason='different')


@pytest.mark.parametrize('state', ['pending', 'deleted'])
def test_deletion_does_not_leave_a_resurrecting_schedule(tmp_path, state):
    backend, service, _ = seed(tmp_path)
    schedule(service)
    backend.delete_request('pump', 'human', 'remove', 1, 'delete')
    if state == 'deleted':
        backend.approve_delete('pump', 'delete')
    result = service.run_due(at=DUE, query_scope=SCOPE)['wake']
    assert result['status'] == ('SKIPPED' if state == 'pending' else 'STALE')
    if state == 'deleted':
        assert backend.get('pump') is None
    else:
        assert backend.get('pump').revision == 1


@pytest.mark.parametrize('nature', ['MOBILE_PRESENCE', 'OBSTACLE'])
def test_mobile_presence_and_obstacle_require_recheck_not_current_truth(tmp_path, nature):
    backend, service, memory = seed(tmp_path)
    memory.metadata['qualification']['nature'] = nature
    backend.update('pump', memory, 1)
    current = backend.get('pump')
    schedule(service, revision=2)
    result = service.run_due(at=LATER, query_scope=SCOPE)['wake']
    changed = backend.get('pump')
    assert result['result']['reason'] == 'RECHECK'
    assert changed.metadata['availability'] == 'INTERMEDIATE' and changed.metadata['recheck_required']
    assert changed.content == current.content and changed.temporal == current.temporal
    assert changed.provenance == current.provenance and changed.metadata['epistemic_status'] == 'CONFIRMED'
    recalled = ContextualRecall(backend).recall('pump', query_scope=SCOPE, at=LATER).items[0]
    assert recalled.needs_review and 'explicit_recheck_required' in recalled.selection_reasons


@pytest.mark.parametrize('reason', ['expired', 'wrong_context', 'refuted'])
def test_inapplicable_reactivation_is_skipped(tmp_path, reason):
    backend, service, memory = seed(tmp_path)
    if reason == 'expired':
        memory.temporal['valid_until'] = CREATED
    if reason == 'refuted':
        memory.metadata['epistemic_status'] = 'REFUTED'
    backend.update('pump', memory, 1)
    schedule(service, revision=2)
    scope = {'project_id': 'other'} if reason == 'wrong_context' else SCOPE
    before = backend.get('pump')
    result = service.run_due(at=DUE, query_scope=scope)['wake']
    assert result['status'] == 'SKIPPED' and backend.get('pump') == before


def test_unknown_context_and_explicit_review_do_not_promote_availability(tmp_path):
    backend, service, _ = seed(tmp_path)
    schedule(service)
    service.run_due(at=DUE)
    assert backend.get('pump').metadata['recheck_required']
    assert backend.get('pump').metadata['availability'] == 'INTERMEDIATE'
    schedule(service, 'review-again', revision=2, kind='RECHECK', due_at=LATER)
    assert service.run_due(at=LATER, query_scope=SCOPE)['review-again']['result']['reason'] == 'RECHECK'


@pytest.mark.parametrize('boundary', ['after_intent', 'after_effect'])
def test_interruption_is_recovered_globally_with_one_event(tmp_path, monkeypatch, boundary):
    backend, service, _ = seed(tmp_path)
    schedule(service)
    def stop(stage):
        if stage == boundary:
            raise RuntimeError('stop')
    monkeypatch.setattr(service, '_checkpoint', stop)
    with pytest.raises(RuntimeError):
        service.run_due(at=DUE, query_scope=SCOPE)
    assert not check_readiness(tmp_path)['ready']
    with pytest.raises(OperationConflict):
        service.cancel('wake', actor='human', at=LATER, reason='too late')
    assert recover_all(tmp_path)['readiness']['ready']
    assert backend.get('pump').revision == 2
    assert service.journal.read('wake')['status'] == 'COMPLETED'
    assert len(list((backend.history_root / 'events/information-write-v1').glob('*.md'))) == 1


def test_interrupted_child_recovers_before_parent_acknowledgement(tmp_path, monkeypatch):
    from core.events.filesystem import FilesystemEventRepository
    backend, service, _ = seed(tmp_path)
    schedule(service)
    with monkeypatch.context() as patch:
        patch.setattr(FilesystemEventRepository, 'save', lambda *a: (_ for _ in ()).throw(RuntimeError('child stop')))
        with pytest.raises(RuntimeError):
            service.run_due(at=DUE, query_scope=SCOPE)
    assert backend.get('pump').revision == 2
    assert recover_all(tmp_path)['readiness']['ready']
    assert service.journal.read('wake')['status'] == 'COMPLETED'
    assert backend.get('pump').revision == 2


def test_source_may_change_before_child_begins_but_never_gets_overwritten(tmp_path, monkeypatch):
    backend, service, memory = seed(tmp_path)
    schedule(service)
    service._checkpoint = lambda stage: (_ for _ in ()).throw(RuntimeError('stop'))
    with pytest.raises(RuntimeError):
        service.run_due(at=DUE, query_scope=SCOPE)
    backend.update('pump', replace(memory, content='New observation'), 1)
    assert recover_all(tmp_path)['readiness']['ready']
    assert service.journal.read('wake')['status'] == 'STALE'
    assert backend.get('pump').content == 'New observation'


def test_acknowledgement_after_compaction_and_deletion_does_not_resurrect(tmp_path):
    backend, service, _ = seed(tmp_path)
    schedule(service)
    def stop(stage):
        if stage == 'after_effect':
            raise RuntimeError('stop')
    service._checkpoint = stop
    with pytest.raises(RuntimeError):
        service.run_due(at=DUE, query_scope=SCOPE)
    writer = FilesystemInformationWrites(backend)
    writer.compact(service.child_ids('wake')[0])
    backend.delete_request('pump', 'human', 'remove', 2, 'delete')
    backend.approve_delete('pump', 'delete')
    assert recover_all(tmp_path)['readiness']['ready']
    assert service.journal.read('wake')['status'] == 'COMPLETED'
    assert backend.get('pump') is None


def test_scheduled_wait_is_readiness_ready_and_recovery_never_runs_it(tmp_path):
    backend, service, memory = seed(tmp_path)
    schedule(service)
    before = hashes(tmp_path)
    assert check_readiness(tmp_path)['ready']
    assert recover_all(tmp_path)['readiness']['ready']
    assert hashes(tmp_path) == before and backend.get('pump') == memory
    # A separate destination is required by the converter's existing contract.
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as separate:
        destination = Path(separate) / 'destination'
        assert convert(tmp_path, destination)['blocked_before_writes']
        assert not destination.exists()


def test_corrupted_trigger_blocks_startup_and_dispatch_without_source_change(tmp_path):
    backend, service, memory = seed(tmp_path)
    schedule(service)
    path = service.journal.path('wake')
    data = json.loads(path.read_text())
    path.write_text(json.dumps(dict(data, format_version=999)))
    assert not check_readiness(tmp_path)['ready']
    with pytest.raises(OperationConflict):
        service.run_due(at=DUE, query_scope=SCOPE)
    assert backend.get('pump') == memory


def test_explicit_level_and_review_ack_preserve_content_and_refresh_catalogue(tmp_path):
    backend, service, memory = seed(tmp_path)
    catalogue = InformationCatalogue(tmp_path)
    catalogue.rebuild()
    command = dict(operation_id='level', event_id='level-event', actor='human', timestamp=DUE)
    availability = AvailabilityService(backend)
    result = availability.set_level(memory, 'HIGH', **command)
    assert availability.set_level(memory, 'HIGH', **command) == result
    assert catalogue.status()['status'] == 'STALE'
    catalogue.rebuild()
    assert catalogue.query(availability='HIGH')[0]['information_id'] == 'pump'
    schedule(service, revision=2, kind='RECHECK')
    service.run_due(at=DUE)
    reviewed = backend.get('pump')
    availability.acknowledge_review(reviewed, operation_id='ack', event_id='ack-event', actor='human', timestamp=LATER)
    current = backend.get('pump')
    assert current.metadata['recheck_required'] is False
    assert current.metadata['epistemic_status'] == memory.metadata['epistemic_status']
    assert current.content == memory.content and current.temporal == memory.temporal
    recalled = ContextualRecall(backend).recall('pump', query_scope=SCOPE, at=LATER, availability='LOW')
    assert not recalled.items


def crash(root, boundary):
    root = Path(root)
    backend = FilesystemBackend(root / 'memory/persistent', root / 'memory/history')
    service = LifecycleTriggers(backend)
    def stop(stage):
        if stage == boundary:
            os._exit(74)
    service._checkpoint = stop
    service.run_due(at=DUE, query_scope=SCOPE)


@pytest.mark.parametrize('boundary', ['after_intent', 'after_effect'])
def test_process_exit_is_resumable(tmp_path, boundary):
    backend, service, _ = seed(tmp_path)
    schedule(service)
    child = multiprocessing.get_context('spawn').Process(target=crash, args=(str(tmp_path), boundary))
    child.start()
    try:
        child.join(15)
        assert child.exitcode == 74
    finally:
        if child.is_alive():
            child.terminate()
            child.join()
    assert recover_all(tmp_path)['readiness']['ready']
    assert backend.get('pump').revision == 2


def test_cli_listing_is_read_only_and_run_due_requires_explicit_time(tmp_path):
    backend, service, _ = seed(tmp_path)
    schedule(service)
    command = [sys.executable, '-B', '-m', 'core.lifecycle.cli', '--root', str(tmp_path)]
    before = hashes(tmp_path)
    listed = subprocess.run([*command, 'list'], text=True, capture_output=True)
    assert listed.returncode == 0 and json.loads(listed.stdout)['wake']['status'] == 'SCHEDULED'
    assert hashes(tmp_path) == before
    result = subprocess.run([*command, 'run-due', '--at', DUE], text=True, capture_output=True)
    assert result.returncode == 0 and json.loads(result.stdout)['wake']['status'] == 'COMPLETED'
    assert backend.get('pump').metadata['recheck_required']
    with pytest.raises(ValueError):
        schedule(service, 'naive', due_at='2026-10-02T06:00:00')


def competitor(root, slot, ready, start):
    root = Path(root)
    backend = FilesystemBackend(root / 'memory/persistent', root / 'memory/history')
    service = LifecycleTriggers(backend)
    ready.set()
    if not start.wait(10):
        raise RuntimeError('start timeout')
    result = service.run_due(at=DUE, query_scope=SCOPE)
    (root / f'worker-{slot}.json').write_text(json.dumps(result))


def test_two_dispatchers_apply_one_effect_and_one_acknowledgement(tmp_path):
    backend, service, _ = seed(tmp_path)
    schedule(service)
    context = multiprocessing.get_context('spawn')
    ready = [context.Event(), context.Event()]
    start = context.Event()
    children = [context.Process(target=competitor, args=(str(tmp_path), i, ready[i], start)) for i in range(2)]
    try:
        for child in children:
            child.start()
        assert all(event.wait(10) for event in ready)
        start.set()
        for child in children:
            child.join(15)
            assert child.exitcode == 0
    finally:
        for child in children:
            if child.is_alive():
                child.terminate()
                child.join()
    results = [json.loads((tmp_path / f'worker-{i}.json').read_text()) for i in range(2)]
    assert sorted(len(result) for result in results) == [0, 1]
    assert backend.get('pump').revision == 2 and service.journal.read('wake')['status'] == 'COMPLETED'


def test_bounded_dispatch_orders_deadlines_and_leaves_remaining_durable(tmp_path):
    backend, service, memory = seed(tmp_path)
    backend.store(replace(memory, information_id='fan'))
    schedule(service, 'later', due_at=LATER)
    service.schedule('fan', revision=1, kind='RECHECK', due_at=DUE, trigger_id='earlier', actor='human', created_at=CREATED)
    assert list(service.run_due(at=LATER, query_scope=SCOPE, limit=1)) == ['earlier']
    assert service.journal.read('later')['status'] == 'SCHEDULED'
    assert list(service.run_due(at=LATER, query_scope=SCOPE, limit=1)) == ['later']
