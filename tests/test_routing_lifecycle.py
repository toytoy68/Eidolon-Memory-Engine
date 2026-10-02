"""Opt-in route lifecycle, legacy compatibility and interleaved recovery."""
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from core.backend.filesystem import FilesystemBackend
from core.information.writes import FilesystemInformationWrites
from core.lifecycle.service import LifecycleTriggers
from core.migration.inventory import inventory
from core.operations.errors import OperationConflict
from core.operations.readiness import check_readiness, recover_all
from core.routing.execution import RoutingExecutor
from core.routing.policy import RoutingContext, TargetRevision
from tests.test_migration_converter import fingerprints
from tests.test_routing_execution import seed, execute, STAMP

DUE = '2026-10-03T08:00:00Z'
SCOPE = {'goal': 'efficiency'}


def prepare(executor, memory, *, project_revision=1, **context):
    return executor.preview(memory, RoutingContext(query_scope=SCOPE, **context),
                            project_revision=project_revision, include_lifecycle=True)


def scheduled(memory):
    return replace(memory, temporal=dict(memory.temporal, resume_at=DUE),
                   metadata=dict(memory.metadata, epistemic_status='CONFIRMED'))


def test_route_registers_deadline_and_persists_availability_in_initial_revision(tmp_path):
    backend, executor, memory = seed(tmp_path)
    memory = scheduled(memory)
    before = fingerprints(tmp_path)
    prepared = prepare(executor, memory)
    assert fingerprints(tmp_path) == before and prepared['format_version'] == 2
    result = execute(executor, prepared)
    current = backend.get('second')
    assert current == replace(memory, metadata=dict(memory.metadata, availability='INTERMEDIATE'))
    assert current.revision == 1 and result['deferred'] == []
    trigger_id = result['lifecycle']['trigger_id']
    lifecycle = LifecycleTriggers(backend)
    trigger = lifecycle.journal.read(trigger_id)
    assert trigger['status'] == 'SCHEDULED' and trigger['command']['revision'] == 1
    assert inventory(tmp_path)['categories']['routing_executions'] == {'routing_execution_v2': 1}
    assert check_readiness(tmp_path)['ready'] and executor.dossiers.status('project')['status'] == 'CURRENT'
    assert lifecycle.run_due(at=STAMP, query_scope=SCOPE) == {}
    assert lifecycle.run_due(at=DUE, query_scope=SCOPE)[trigger_id]['status'] == 'COMPLETED'
    assert backend.get('second').revision == 2 and backend.get('second').metadata['availability'] == 'HIGH'
    stable = fingerprints(tmp_path)
    assert execute(executor, prepared) == result and lifecycle.run_due(at=DUE, query_scope=SCOPE) == {}
    assert fingerprints(tmp_path) == stable
    assert executor.dossiers.status('project')['status'] == 'STALE'  # explicit reconcile remains required


@pytest.mark.parametrize('nature,level,recheck', [('TECHNICAL', 'LOW', False), ('OBSTACLE', 'HIGH', True)])
def test_unscheduled_route_applies_policy_without_extra_event_or_truth_promotion(tmp_path, nature, level, recheck):
    backend, executor, memory = seed(tmp_path)
    labels = dict(memory.metadata['qualification'], nature=nature, horizon='LONG_TERM')
    memory = replace(memory, metadata=dict(memory.metadata, qualification=labels))
    result = execute(executor, prepare(executor, memory))
    stored = backend.get('second')
    assert stored.metadata['availability'] == level
    assert bool(stored.metadata.get('recheck_required')) == recheck
    assert stored.metadata['epistemic_status'] == 'UNVERIFIED' and stored.content == memory.content
    assert stored.revision == 1 and result['lifecycle']['trigger_id'] is None
    assert LifecycleTriggers(backend).journal.ids() == []
    assert len(list((backend.history_root / 'events/information-write-v1').glob('*.md'))) == 1


@pytest.mark.parametrize('boundary', ['before_information', 'after_information', 'after_project', 'after_projection', 'after_trigger'])
def test_every_route_boundary_recovers_once_with_one_deadline(tmp_path, monkeypatch, boundary):
    backend, executor, memory = seed(tmp_path)
    prepared = prepare(executor, scheduled(memory))
    def stop(stage):
        if stage == boundary:
            raise RuntimeError('stop')
    with monkeypatch.context() as patch:
        patch.setattr(executor, '_checkpoint', stop)
        with pytest.raises(RuntimeError, match='stop'):
            execute(executor, prepared)
    assert not check_readiness(tmp_path)['ready']
    assert recover_all(tmp_path)['readiness']['ready']
    result = execute(executor, prepared)
    assert backend.get('second').revision == 1 and executor.storage.get('project').revision == 2
    assert LifecycleTriggers(backend).journal.ids() == [result['lifecycle']['trigger_id']]
    assert executor.dossiers.status('project')['status'] == 'CURRENT'


def interrupt_after_registration(executor, prepared, monkeypatch):
    def stop(stage):
        if stage == 'after_trigger':
            raise RuntimeError('stop')
    with monkeypatch.context() as patch:
        patch.setattr(executor, '_checkpoint', stop)
        with pytest.raises(RuntimeError):
            execute(executor, prepared)
    return LifecycleTriggers(executor.backend), executor.child_id('intent', 'trigger')


def test_due_dispatch_waits_for_parent_receipt_then_recovers_without_cycle(tmp_path, monkeypatch):
    backend, executor, memory = seed(tmp_path)
    prepared = prepare(executor, scheduled(memory))
    lifecycle, trigger_id = interrupt_after_registration(executor, prepared, monkeypatch)
    with pytest.raises(OperationConflict):
        lifecycle.run_due(at=DUE, query_scope=SCOPE)
    assert lifecycle.journal.read(trigger_id)['status'] == 'SCHEDULED'
    assert backend.get('second').revision == 1
    assert recover_all(tmp_path)['readiness']['ready']
    assert lifecycle.journal.read(trigger_id)['status'] == 'SCHEDULED'
    assert lifecycle.run_due(at=DUE, query_scope=SCOPE)[trigger_id]['status'] == 'COMPLETED'
    assert backend.get('second').revision == 2


def test_cancellation_between_registration_and_receipt_is_preserved(tmp_path, monkeypatch):
    backend, executor, memory = seed(tmp_path)
    prepared = prepare(executor, scheduled(memory))
    lifecycle, trigger_id = interrupt_after_registration(executor, prepared, monkeypatch)
    cancelled = lifecycle.cancel(trigger_id, actor='human', at=STAMP, reason='changed plans')
    assert recover_all(tmp_path)['readiness']['ready']
    assert execute(executor, prepared)['lifecycle']['trigger_id'] == trigger_id
    assert lifecycle.journal.read(trigger_id) == cancelled
    assert lifecycle.run_due(at=DUE, query_scope=SCOPE) == {} and backend.get('second').revision == 1


def test_routed_correction_invalidates_old_deadline_and_schedules_new_revision(tmp_path):
    backend, executor, memory = seed(tmp_path)
    original = execute(executor, prepare(executor, scheduled(memory)))
    old = backend.get('second')
    corrected = replace(old, content='corrected 210 W')
    result = execute(executor, prepare(executor, corrected, project_revision=2,
                     update_target=TargetRevision('second', 1)), 'correction')
    lifecycle = LifecycleTriggers(backend)
    assert result['information']['revision'] == 2 and result['project']['revision'] == 2
    assert lifecycle.journal.read(result['lifecycle']['trigger_id'])['command']['revision'] == 2
    outcomes = lifecycle.run_due(at=DUE, query_scope=SCOPE)
    assert outcomes[original['lifecycle']['trigger_id']]['status'] == 'STALE'
    assert outcomes[result['lifecycle']['trigger_id']]['status'] == 'COMPLETED'
    assert backend.get('second').revision == 3 and backend.get('second').content == 'corrected 210 W'


@pytest.mark.parametrize('due', ['not-a-date', '2026-10-03T08:00:00'])
def test_invalid_deadline_is_refused_during_readonly_preview(tmp_path, due):
    backend, executor, memory = seed(tmp_path)
    before = fingerprints(tmp_path)
    with pytest.raises(ValueError):
        prepare(executor, replace(memory, temporal={'resume_at': due}))
    assert fingerprints(tmp_path) == before and backend.get('second') is None


def test_bad_execution_time_or_unrelated_pending_route_refused_before_reservation(tmp_path, monkeypatch):
    backend, executor, memory = seed(tmp_path)
    prepared = prepare(executor, scheduled(memory))
    with pytest.raises(ValueError):
        executor.execute(prepared, intent_id='bad-time', actor='human', timestamp='yesterday')
    assert not executor.journal.path('bad-time').exists()
    legacy = executor.preview(replace(memory, information_id='other'), RoutingContext(query_scope=SCOPE), project_revision=1)
    with monkeypatch.context() as patch:
        patch.setattr(executor, '_checkpoint', lambda stage: (_ for _ in ()).throw(RuntimeError('stop')))
        with pytest.raises(RuntimeError):
            execute(executor, legacy, 'legacy')
    with pytest.raises(OperationConflict):
        execute(executor, prepared)
    assert not executor.journal.path('intent').exists() and backend.get('second') is None


def test_unrelated_corruption_is_not_exempted_by_route_ownership(tmp_path, monkeypatch):
    backend, executor, memory = seed(tmp_path)
    prepared = prepare(executor, scheduled(memory))
    def corrupt(stage):
        if stage == 'after_projection':
            executor.journal.path('bad').write_text('{bad')
    with monkeypatch.context() as patch:
        patch.setattr(executor, '_checkpoint', corrupt)
        with pytest.raises(OperationConflict):
            execute(executor, prepared)
    assert LifecycleTriggers(backend).journal.ids() == []
    assert not recover_all(tmp_path)['readiness']['ready']
    executor.journal.path('bad').unlink()  # remove the injected corruption
    assert recover_all(tmp_path)['readiness']['ready']


def test_receipt_replay_after_deletion_does_not_recreate_source_or_deadline(tmp_path):
    backend, executor, memory = seed(tmp_path)
    prepared = prepare(executor, scheduled(memory))
    result = execute(executor, prepared)
    lifecycle = LifecycleTriggers(backend)
    lifecycle.cancel(result['lifecycle']['trigger_id'], actor='human', at=STAMP, reason='remove')
    executor.storage.delete('project', previous_revision=2, operation_id='delete-project')
    FilesystemInformationWrites(backend).compact(executor.child_id('intent', 'information'))
    backend.delete_request('second', 'human', 'remove', 1, 'delete')
    backend.approve_delete('second', 'delete')
    stable = fingerprints(tmp_path)
    assert execute(executor, prepared) == result
    assert fingerprints(tmp_path) == stable and backend.get('second') is None
    assert lifecycle.journal.read(result['lifecycle']['trigger_id'])['status'] == 'CANCELLED'


def crash(root, plan, boundary):
    root = Path(root)
    executor = RoutingExecutor(FilesystemBackend(root / 'memory/persistent', root / 'memory/history'))
    def stop(stage):
        if stage == boundary:
            os._exit(74)
    executor._checkpoint = stop
    execute(executor, json.loads(Path(plan).read_text()))


@pytest.mark.parametrize('boundary', ['after_information', 'after_trigger'])
def test_real_process_exit_is_recoverable(tmp_path, boundary):
    backend, executor, memory = seed(tmp_path)
    prepared = prepare(executor, scheduled(memory))
    plan = tmp_path / 'input-plan.json'
    plan.write_text(json.dumps(prepared))
    script = 'from tests.test_routing_lifecycle import crash; import sys; crash(*sys.argv[1:])'
    child = subprocess.run([sys.executable, '-B', '-c', script, str(tmp_path), str(plan), boundary], timeout=30)
    assert child.returncode == 74
    assert recover_all(tmp_path)['readiness']['ready']
    assert backend.get('second').revision == 1 and len(LifecycleTriggers(backend).journal.ids()) == 1


def test_cli_opt_in_preview_remains_readonly_then_executes(tmp_path, capsys):
    from core.routing.execution_cli import main
    backend, executor, memory = seed(tmp_path)
    source, context, plan = (tmp_path / name for name in ['input.json', 'context.json', 'plan.json'])
    source.write_text(json.dumps(asdict(scheduled(memory))))
    context.write_text(json.dumps({'query_scope': SCOPE}))
    before = fingerprints(tmp_path)
    assert main(['--root', str(tmp_path), 'preview', '--memory', str(source), '--context', str(context),
                 '--project-revision', '1', '--with-lifecycle']) == 0
    assert fingerprints(tmp_path) == before
    prepared = json.loads(capsys.readouterr().out)
    assert prepared['format_version'] == 2
    plan.write_text(json.dumps(prepared))
    assert main(['--root', str(tmp_path), 'execute', '--plan', str(plan), '--intent-id', 'cli',
                 '--actor', 'human', '--timestamp', STAMP]) == 0
    result = json.loads(capsys.readouterr().out)
    assert LifecycleTriggers(backend).journal.read(result['lifecycle']['trigger_id'])['status'] == 'SCHEDULED'
