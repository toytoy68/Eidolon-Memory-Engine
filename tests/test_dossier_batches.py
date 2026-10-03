"""Bound publications while retaining whole-tree validation and restart discovery."""
import json

import pytest

from core.dossiers.cli import main as dossier_cli
from core.dossiers.projects import END
from core.dossiers.reconciliation import DossierReconciler
from core.maintenance.cli import main as maintenance_cli
from core.maintenance.service import MaintenancePass
from core.threads.models import Thread
from tests.test_dossier_reconciliation import seed, update, STAMP
from tools.vm_acceptance import hashes


def setup(root):
    backend, storage, dossiers = seed(root)
    for identity in ('aaa', 'bbb'):
        storage.create(Thread(identity, identity, 'Shared source',
                              relations=[{'type': 'CONCERNS', 'target_id': 'info-1'}]))
    return backend, dossiers, DossierReconciler(dossiers)


def test_bounded_missing_views_converge_in_order_without_canonical_changes(tmp_path):
    backend, dossiers, reconciler = setup(tmp_path)
    before = hashes(backend.persistent_root), hashes(backend.history_root)
    for identity, remaining in [('aaa', 2), ('bbb', 1), ('thread-cooling', 0)]:
        result = reconciler.apply(limit=1)
        assert [a['thread_id'] for a in result['actions']] == [identity]
        assert result['remaining_count'] == remaining
        assert result['status'] == ('PARTIAL' if remaining else 'RECONCILED')
    assert (hashes(backend.persistent_root), hashes(backend.history_root)) == before
    assert reconciler.apply(limit=1)['actions'] == []


@pytest.mark.parametrize('limit', [0, -1, 101, True, 1.5, '1'])
def test_invalid_bound_fails_before_any_write(tmp_path, limit):
    _, _, reconciler = setup(tmp_path)
    before = hashes(tmp_path)
    with pytest.raises(ValueError):
        reconciler.apply(limit=limit)
    assert hashes(tmp_path) == before


def test_corruption_beyond_first_batch_blocks_all_publications(tmp_path):
    _, dossiers, reconciler = setup(tmp_path)
    reconciler.apply()
    path = dossiers._path('thread-cooling')
    path.write_text(path.read_text().replace(END, ''))
    dossiers._path('aaa').unlink()
    before = hashes(tmp_path)
    result = reconciler.apply(limit=1)
    assert result['status'] == 'BLOCKED' and result['actions'] == []
    assert hashes(tmp_path) == before


def test_restart_rediscovers_work_and_preserves_human_sections(tmp_path, monkeypatch):
    backend, dossiers, reconciler = setup(tmp_path)
    reconciler.apply()
    path = dossiers._path('aaa')
    path.write_bytes(b'Human note\r\n' + path.read_bytes())
    update(backend, 'Corrected evidence')
    rebuild = dossiers.rebuild
    def stop(identity):
        rebuild(identity)
        raise RuntimeError('publication completed before interruption')
    with monkeypatch.context() as patch:
        patch.setattr(dossiers, 'rebuild', stop)
        with pytest.raises(RuntimeError):
            reconciler.apply(limit=1)
    assert path.read_bytes().startswith(b'Human note\r\n')
    result = reconciler.apply(limit=1)
    assert [a['thread_id'] for a in result['actions']] == ['bbb']
    assert result['remaining_count'] == 1
    assert reconciler.apply(limit=1)['status'] == 'RECONCILED'


def test_maintenance_reports_partial_until_dossiers_are_current(tmp_path):
    backend, _, _ = setup(tmp_path)
    service = MaintenancePass(tmp_path)
    for remaining in (2, 1, 0):
        result = service.run(at=STAMP, dossier_limit=1)
        assert result['status'] == ('PARTIAL' if remaining else 'COMPLETED'), result
        assert len(result['dossiers']['actions']) == 1
        assert result['verification']['catalogue']['status'] == 'CURRENT'
        assert result['dossiers']['remaining_count'] == remaining
    assert service.run(at=STAMP, dossier_limit=1)['dossiers']['actions'] == []
    assert backend.get('info-1').revision == 1


def test_cli_exposes_partial_and_inspection_stays_read_only(tmp_path, capsys):
    setup(tmp_path)
    root = ['--root', str(tmp_path)]
    before = hashes(tmp_path)
    assert dossier_cli(root + ['reconcile', '--limit', '1']) == 1
    assert json.loads(capsys.readouterr().out)['status'] == 'DRIFT'
    assert hashes(tmp_path) == before
    assert dossier_cli(root + ['reconcile', '--apply', '--limit', '1']) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'PARTIAL'
    assert maintenance_cli(root + ['run', '--at', STAMP, '--dossier-limit', '1']) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'PARTIAL'


def test_orphaned_view_is_cleaned_with_notes_preserved(tmp_path):
    _, dossiers, reconciler = setup(tmp_path)
    reconciler.apply()
    path = dossiers._path('aaa')
    path.write_bytes(b'Keep this human note\r\n' + path.read_bytes())
    dossiers.storage.delete('aaa', previous_revision=1, operation_id='remove-aaa')
    result = reconciler.apply(limit=1)
    assert result['status'] == 'RECONCILED'
    assert result['actions'][0]['status'] == 'SOURCE_REMOVED'
    assert path.read_bytes().startswith(b'Keep this human note\r\n')
    assert 'Une pompe à tester.' not in path.read_text()


def test_false_success_does_not_hide_remaining_dossiers(tmp_path, monkeypatch):
    _, _, _ = setup(tmp_path)
    service = MaintenancePass(tmp_path)
    monkeypatch.setattr(service.dossiers, 'apply', lambda **kwargs: dict(status='RECONCILED', actions=[]))
    result = service.run(at=STAMP, dossier_limit=1)
    assert result['status'] == 'BLOCKED'
    assert result['verification']['dossiers']['status'] == 'DRIFT'


def bounded_worker(root, output):
    from pathlib import Path
    from tests.test_dossier_reconciliation import open_dossiers
    output.put(DossierReconciler(open_dossiers(Path(root))).apply(limit=1))


def test_two_bounded_workers_do_distinct_durable_work(tmp_path):
    import multiprocessing
    _, _, reconciler = setup(tmp_path)
    context = multiprocessing.get_context('fork')
    output = context.Queue()
    workers = [context.Process(target=bounded_worker, args=(str(tmp_path), output)) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(20)
        assert worker.exitcode == 0
    reports = [output.get(timeout=3) for _ in workers]
    assert {report['actions'][0]['thread_id'] for report in reports} == {'aaa', 'bbb'}
    assert all(report['status'] == 'PARTIAL' for report in reports)
    assert reconciler.apply(limit=1)['status'] == 'RECONCILED'
