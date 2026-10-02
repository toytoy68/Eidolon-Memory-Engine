"""End-to-end maintenance, convergent restart and durable bounded work."""
from dataclasses import replace
import json
import multiprocessing
import os
from pathlib import Path

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.indexing.catalogue import InformationCatalogue
from core.lifecycle.service import LifecycleTriggers
from core.maintenance.service import MaintenancePass
from core.operations.readiness import check_readiness
from core.routing.execution import RoutingExecutor
from tests.test_migration_converter import fingerprints
from tests.test_routing_execution import seed as route_seed, execute, STAMP
from tests.test_routing_lifecycle import prepare, scheduled, DUE, SCOPE


def seed(root):
    backend, executor, memory = route_seed(root)
    result = execute(executor, prepare(executor, scheduled(memory)))
    InformationCatalogue(root).rebuild()
    path = executor.dossiers._path('project')
    path.write_text(path.read_text() + '\nHuman maintenance note.\n')
    return backend, MaintenancePass(root), result['lifecycle']['trigger_id']


def test_inspection_writes_nothing_and_reports_future_and_due_work(tmp_path):
    backend, service, trigger = seed(tmp_path)
    before = fingerprints(tmp_path)
    early = service.inspect(at=STAMP)
    assert early['status'] == 'READY' and not early['work_pending']
    assert early['deadlines']['future_count'] == 1 and early['deadlines']['next_due_at'] == DUE
    due = service.inspect(at=DUE)
    assert due['work_pending'] and due['deadlines']['due'][0]['trigger_id'] == trigger
    assert fingerprints(tmp_path) == before and backend.get('second').revision == 1


def test_pass_dispatches_then_reconciles_views_and_replay_changes_nothing(tmp_path):
    backend, service, trigger = seed(tmp_path)
    result = service.run(at=DUE, query_scope=SCOPE)
    assert result['status'] == 'COMPLETED' and result['triggers'][trigger]['reason'] == 'HIGH'
    assert backend.get('second').revision == 2
    final = result['verification']
    assert final['dossiers']['status'] == 'CLEAN' and final['catalogue']['status'] == 'CURRENT'
    assert service.catalogue.query(availability='HIGH')[0]['information_id'] == 'second'
    dossier = (tmp_path / 'memory/dossiers/project.md').read_text()
    assert 'second` revision 2' in dossier and 'Human maintenance note.' in dossier
    assert 'measure 200 W' in dossier and 'CONFIRMED' in dossier
    stable = fingerprints(tmp_path)
    replay = MaintenancePass(tmp_path).run(at=DUE, query_scope=SCOPE)
    assert replay['status'] == 'COMPLETED' and replay['triggers'] == {}
    assert replay['dossiers']['actions'] == [] and replay['catalogue']['status'] == 'UNCHANGED'
    assert fingerprints(tmp_path) == stable


@pytest.mark.parametrize('boundary', ['after_recovery', 'after_triggers', 'after_dossiers', 'after_catalogue'])
def test_restart_after_each_durable_stage_converges_without_second_effect(tmp_path, monkeypatch, boundary):
    backend, service, trigger = seed(tmp_path)
    def stop(stage):
        if stage == boundary:
            raise RuntimeError('stop')
    with monkeypatch.context() as patch:
        patch.setattr(service, '_checkpoint', stop)
        with pytest.raises(RuntimeError):
            service.run(at=DUE, query_scope=SCOPE)
    result = MaintenancePass(tmp_path).run(at=DUE, query_scope=SCOPE)
    assert result['status'] == 'COMPLETED' and backend.get('second').revision == 2
    assert not service.inspect(at=DUE)['work_pending']
    assert 'Human maintenance note.' in (tmp_path / 'memory/dossiers/project.md').read_text()


def test_pass_recovers_route_parent_before_its_due_child(tmp_path, monkeypatch):
    backend, executor, memory = route_seed(tmp_path)
    prepared = prepare(executor, scheduled(memory))
    def stop(stage):
        if stage == 'after_trigger':
            raise RuntimeError('stop')
    with monkeypatch.context() as patch:
        patch.setattr(executor, '_checkpoint', stop)
        with pytest.raises(RuntimeError):
            execute(executor, prepared)
    service = MaintenancePass(tmp_path)
    before = fingerprints(tmp_path)
    assert service.inspect(at=DUE)['status'] == 'BLOCKED'
    assert fingerprints(tmp_path) == before
    result = service.run(at=DUE, query_scope=SCOPE)
    assert result['status'] == 'COMPLETED' and result['recovery']['readiness']['ready']
    assert result['recovery']['routing-executions']['intent']['status'] == 'COMMITTED'
    assert backend.get('second').revision == 2 and executor.storage.get('project').revision == 2


def test_due_limit_leaves_durable_backlog_and_rebuilds_after_each_pass(tmp_path):
    backend, service, first = seed(tmp_path)
    memory = backend.get('second')
    backend.store(replace(memory, information_id='third'))
    service.lifecycle.schedule('third', revision=1, kind='RECHECK', due_at=DUE,
                               trigger_id='z-last', actor='human', created_at=STAMP)
    one = service.run(at=DUE, query_scope=SCOPE, limit=1)
    assert one['status'] == 'PARTIAL' and len(one['verification']['deadlines']['due']) == 1
    assert one['verification']['catalogue']['status'] == 'CURRENT'
    assert backend.get('second').revision == 2 and backend.get('third').revision == 1
    two = service.run(at=DUE, query_scope=SCOPE, limit=1)
    assert two['status'] == 'COMPLETED' and backend.get('third').revision == 2
    assert service.catalogue.query(availability='INTERMEDIATE')[0]['recheck_required']


def test_future_deadline_and_unknown_scope_never_invent_current_context(tmp_path):
    backend, service, trigger = seed(tmp_path)
    early = service.run(at=STAMP)
    assert early['status'] == 'COMPLETED' and early['triggers'] == {}
    assert service.lifecycle.journal.read(trigger)['status'] == 'SCHEDULED'
    due = service.run(at=DUE)
    assert due['triggers'][trigger]['reason'] == 'RECHECK'
    current = backend.get('second')
    assert current.metadata['recheck_required'] and current.metadata['availability'] == 'INTERMEDIATE'
    assert current.metadata['epistemic_status'] == 'CONFIRMED'


def test_corrupt_journal_blocks_whole_pass_without_writes(tmp_path):
    backend, service, trigger = seed(tmp_path)
    service.lifecycle.journal.path('broken').write_text('{broken')
    before = fingerprints(tmp_path)
    report = service.run(at=DUE, query_scope=SCOPE)
    assert report['status'] == 'BLOCKED' and report['stage'] == 'readiness'
    assert fingerprints(tmp_path) == before and backend.get('second').revision == 1


def test_damaged_human_boundary_blocks_after_effect_then_relaunch_repairs(tmp_path):
    backend, service, trigger = seed(tmp_path)
    path = tmp_path / 'memory/dossiers/project.md'
    original = path.read_text()
    damaged = original.replace('<!-- END MEMORY-ENGINE GENERATED -->', '')
    path.write_text(damaged)
    report = service.run(at=DUE, query_scope=SCOPE)
    assert report['status'] == 'BLOCKED' and report['stage'] == 'dossiers'
    assert backend.get('second').revision == 2 and path.read_text() == damaged
    assert service.catalogue.status()['status'] == 'STALE'
    path.write_text(original)  # human restores the known boundary, never guessed by the pass
    assert service.run(at=DUE, query_scope=SCOPE)['status'] == 'COMPLETED'
    assert backend.get('second').revision == 2 and 'Human maintenance note.' in path.read_text()


def test_final_disk_check_rejects_a_false_rebuild_success(tmp_path, monkeypatch):
    backend, service, trigger = seed(tmp_path)
    monkeypatch.setattr(service.catalogue, 'rebuild', lambda: {'status': 'REBUILT'})
    result = service.run(at=DUE, query_scope=SCOPE)
    assert result['status'] == 'BLOCKED' and result['stage'] == 'verification'
    assert result['verification']['catalogue']['status'] == 'STALE'
    assert backend.get('second').revision == 2


def test_pending_delete_is_not_approved_and_catalogue_query_excludes_it(tmp_path):
    backend, service, trigger = seed(tmp_path)
    backend.delete_request('second', 'human', 'remove later', 1, 'delete')
    result = service.run(at=DUE, query_scope=SCOPE)
    assert result['status'] == 'COMPLETED' and result['triggers'][trigger]['status'] == 'SKIPPED'
    assert backend.get('second').revision == 1
    assert service.catalogue.query('second') == []
    assert json.loads((backend.pending_delete_root / 'second.json').read_text())['status'] == 'PENDING_DELETE'


def crash(root, boundary):
    service = MaintenancePass(Path(root))
    def stop(stage):
        if stage == boundary:
            os._exit(74)
    service._checkpoint = stop
    service.run(at=DUE, query_scope=SCOPE)


@pytest.mark.parametrize('boundary', ['after_triggers', 'after_dossiers'])
def test_real_process_stop_is_recovered_by_relaunch(tmp_path, boundary):
    backend, service, _ = seed(tmp_path)
    child = multiprocessing.get_context('spawn').Process(target=crash, args=(str(tmp_path), boundary))
    child.start()
    try:
        child.join(20)
        assert child.exitcode == 74
    finally:
        if child.is_alive():
            child.terminate()
            child.join()
    assert MaintenancePass(tmp_path).run(at=DUE, query_scope=SCOPE)['status'] == 'COMPLETED'
    assert backend.get('second').revision == 2 and not service.inspect(at=DUE)['work_pending']


def compete(root, number, ready, start):
    service = MaintenancePass(Path(root))
    ready.set()
    if not start.wait(10):
        raise RuntimeError('start timeout')
    report = service.run(at=DUE, query_scope=SCOPE)
    (Path(root) / f'worker-{number}.json').write_text(json.dumps(report))


def test_two_maintenance_workers_converge_to_one_effect(tmp_path):
    backend, service, _ = seed(tmp_path)
    context = multiprocessing.get_context('spawn')
    ready = [context.Event(), context.Event()]
    start = context.Event()
    children = [context.Process(target=compete, args=(str(tmp_path), i, ready[i], start)) for i in range(2)]
    try:
        for child in children:
            child.start()
        assert all(event.wait(10) for event in ready)
        start.set()
        for child in children:
            child.join(20)
            assert child.exitcode == 0
    finally:
        for child in children:
            if child.is_alive():
                child.terminate()
                child.join()
    reports = [json.loads((tmp_path / f'worker-{i}.json').read_text()) for i in range(2)]
    assert all(report['status'] == 'COMPLETED' for report in reports)
    assert sorted(len(report['triggers']) for report in reports) == [0, 1]
    assert backend.get('second').revision == 2 and not service.inspect(at=DUE)['work_pending']


def test_cli_inspection_no_writes_and_blocked_run_is_nonzero(tmp_path, capsys):
    from core.maintenance.cli import main
    _, service, _ = seed(tmp_path)
    before = fingerprints(tmp_path)
    assert main(['--root', str(tmp_path), 'inspect', '--at', DUE]) == 0
    assert json.loads(capsys.readouterr().out)['work_pending']
    assert fingerprints(tmp_path) == before
    service.lifecycle.journal.path('bad').write_text('{bad')
    assert main(['--root', str(tmp_path), 'run', '--at', DUE]) == 1
    assert json.loads(capsys.readouterr().out)['status'] == 'BLOCKED'


def test_cli_run_and_invalid_clock(tmp_path, capsys):
    from core.maintenance.cli import main
    backend, service, trigger = seed(tmp_path)
    before = fingerprints(tmp_path)
    assert main(['--root', str(tmp_path), 'run', '--at', '2026-10-03T08:00:00']) == 1
    assert fingerprints(tmp_path) == before
    capsys.readouterr()
    scope = tmp_path / 'scope.json'
    scope.write_text(json.dumps(SCOPE))
    assert main(['--root', str(tmp_path), 'run', '--at', DUE, '--scope', str(scope)]) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'COMPLETED'
    assert backend.get('second').revision == 2


def test_pass_recovers_interrupted_effect_ack_before_rebuilding(tmp_path, monkeypatch):
    backend, service, trigger = seed(tmp_path)
    def stop(stage):
        if stage == 'after_effect':
            raise RuntimeError('stop')
    with monkeypatch.context() as patch:
        patch.setattr(service.lifecycle, '_checkpoint', stop)
        with pytest.raises(RuntimeError):
            service.run(at=DUE, query_scope=SCOPE)
    assert backend.get('second').revision == 2 and not check_readiness(tmp_path)['ready']
    result = MaintenancePass(tmp_path).run(at=DUE, query_scope=SCOPE)
    assert result['status'] == 'COMPLETED' and result['triggers'] == {}
    assert result['recovery']['lifecycle-triggers'][trigger]['status'] == 'COMPLETED'
    assert backend.get('second').revision == 2 and not service.inspect(at=DUE)['work_pending']


def test_canonical_deletion_refreshes_orphaned_view_without_erasing_human_notes(tmp_path):
    from core.information.writes import FilesystemInformationWrites
    backend, service, trigger = seed(tmp_path)
    executor = RoutingExecutor(backend)
    executor.storage.delete('project', previous_revision=2, operation_id='delete-project')
    FilesystemInformationWrites(backend).compact(executor.child_id('intent', 'information'))
    backend.delete_request('second', 'human', 'remove', 1, 'delete-second')
    backend.approve_delete('second', 'delete-second')
    report = service.run(at=DUE, query_scope=SCOPE)
    assert report['status'] == 'COMPLETED' and report['triggers'][trigger]['status'] == 'STALE'
    assert backend.get('second') is None and service.catalogue.query('second') == []
    text = (tmp_path / 'memory/dossiers/project.md').read_text()
    assert 'measure 200 W' not in text and 'Human maintenance note.' in text
    assert 'Thread source absent' in text
