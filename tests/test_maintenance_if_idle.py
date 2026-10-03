"""Explicit lock occupancy deferral; no VM load or inactivity inference."""
from contextlib import contextmanager
import json
import multiprocessing
from pathlib import Path

import pytest

from core.maintenance.cli import main
from core.maintenance.service import MaintenancePass
from core.persistence import exclusive_write
from tests.test_maintenance_pass import seed, DUE, SCOPE
from tools.vm_acceptance import hashes


def hold(root, ready, release):
    with exclusive_write(Path(root)):
        ready.set()
        if not release.wait(20):
            raise RuntimeError('test lock release timed out')


@contextmanager
def occupied(root):
    context = multiprocessing.get_context('fork')
    ready, release = context.Event(), context.Event()
    process = context.Process(target=hold, args=(str(root), ready, release))
    process.start()
    try:
        assert ready.wait(5)
        yield
    finally:
        release.set()
        process.join(5)
        if process.is_alive():
            process.terminate()
            process.join(5)
        assert process.exitcode == 0


@pytest.mark.parametrize('which', ['persistent', 'threads'])
def test_busy_canonical_writer_defers_before_effects_and_retry_finishes(tmp_path, which):
    backend, service, trigger = seed(tmp_path)
    root = backend.persistent_root if which == 'persistent' else service.storage.threads_root
    with occupied(root):
        before = hashes(tmp_path)
        result = service.run(at=DUE, query_scope=SCOPE, if_idle=True)
        assert result['status'] == 'DEFERRED'
        assert result['reason'] == 'CANONICAL_WRITER_BUSY'
        assert result['recovery'] is None and result['triggers'] == {}
        assert result['dossiers'] is None and result['verification'] is None
        assert hashes(tmp_path) == before
        assert backend.get('second').revision == 1
    done = service.run(at=DUE, query_scope=SCOPE, if_idle=True)
    assert done['status'] == 'COMPLETED'
    assert backend.get('second').revision == 2
    assert service.run(at=DUE, query_scope=SCOPE, if_idle=True)['triggers'] == {}


def test_failed_second_lock_releases_first_lock(tmp_path):
    backend, service, _ = seed(tmp_path)
    with occupied(service.storage.threads_root):
        assert service.run(at=DUE, if_idle=True)['status'] == 'DEFERRED'
        from core.persistence import write_lock_held
        assert not write_lock_held(backend.persistent_root)
        # Another process can immediately acquire the first lock after deferral.
        with occupied(backend.persistent_root):
            pass


def test_same_thread_owned_lock_is_reentrant(tmp_path):
    backend, service, _ = seed(tmp_path)
    with exclusive_write(backend.persistent_root):
        assert service.run(at=DUE, query_scope=SCOPE, if_idle=True)['status'] == 'COMPLETED'
    assert backend.get('second').revision == 2


def test_deferred_cli_is_explicit_successful_retryable_result(tmp_path, capsys):
    backend, service, _ = seed(tmp_path)
    with occupied(backend.persistent_root):
        assert main(['--root', str(tmp_path), 'run', '--at', DUE, '--if-idle']) == 0
        result = json.loads(capsys.readouterr().out)
        assert result['status'] == 'DEFERRED'
        assert result['reason'] == 'CANONICAL_WRITER_BUSY'


@pytest.mark.parametrize('value', [None, 1, 'true'])
def test_invalid_idle_option_does_not_write(tmp_path, value):
    _, service, _ = seed(tmp_path)
    before = hashes(tmp_path)
    with pytest.raises(ValueError):
        service.run(at=DUE, if_idle=value)
    assert hashes(tmp_path) == before


def test_free_idle_option_keeps_blocking_readiness_checks(tmp_path):
    backend, service, _ = seed(tmp_path)
    path = service.lifecycle.journal.path('unknown')
    path.write_text('{')
    before = hashes(tmp_path)
    result = service.run(at=DUE, if_idle=True)
    assert result['status'] == 'BLOCKED' and not result['readiness']['ready']
    assert hashes(tmp_path) == before
    assert backend.get('second').revision == 1


def test_busy_defers_without_scanning_in_flight_journals(tmp_path, monkeypatch):
    import core.maintenance.service as module
    backend, service, _ = seed(tmp_path)
    def forbidden(*args):
        raise AssertionError('readiness must wait until canonical locks are owned')
    monkeypatch.setattr(module, 'check_readiness', forbidden)
    with occupied(backend.persistent_root):
        assert service.run(at=DUE, if_idle=True)['status'] == 'DEFERRED'


def test_unsafe_lock_is_blocked_instead_of_reported_busy(tmp_path):
    backend, service, _ = seed(tmp_path)
    lock = backend.persistent_root / '.write.lock'
    lock.unlink()
    outside = tmp_path / 'outside-lock'
    outside.write_text('preserve')
    lock.symlink_to(outside)
    result = service.run(at=DUE, if_idle=True)
    assert result['status'] == 'BLOCKED'
    assert result['error']['type'] == 'ValueError'
    assert outside.read_text() == 'preserve'


def test_idle_option_retains_partial_dossier_backlog(tmp_path):
    from tests.test_dossier_batches import setup
    backend, _, _ = setup(tmp_path)
    service = MaintenancePass(tmp_path)
    result = service.run(at=DUE, if_idle=True, dossier_limit=1)
    assert result['status'] == 'PARTIAL'
    assert result['dossiers']['remaining_count'] == 2
    assert backend.get('info-1').revision == 1


@pytest.mark.parametrize('if_idle', [False, True])
def test_readiness_runs_only_after_canonical_locks(tmp_path, monkeypatch, if_idle):
    from core.persistence import write_lock_held
    import core.maintenance.service as module
    backend, service, _ = seed(tmp_path)
    original = module.check_readiness
    checks = []

    def checked(root):
        assert write_lock_held(backend.persistent_root)
        assert write_lock_held(service.storage.threads_root)
        checks.append(root)
        return original(root)

    monkeypatch.setattr(module, 'check_readiness', checked)
    assert service.run(at=DUE, query_scope=SCOPE, if_idle=if_idle)['status'] == 'COMPLETED'
    assert checks


@pytest.mark.parametrize('if_idle', [False, True])
def test_deadline_read_failure_reports_readiness_stage(tmp_path, monkeypatch, if_idle):
    _, service, _ = seed(tmp_path)

    def broken(at):
        raise ValueError('deadline read failed')

    monkeypatch.setattr(service, '_deadlines', broken)
    result = service.run(at=DUE, if_idle=if_idle)
    assert result['status'] == 'BLOCKED'
    assert result['stage'] == 'readiness'


@pytest.mark.parametrize('if_idle', [False, True])
def test_idle_pass_reuses_one_full_inventory(tmp_path, monkeypatch, if_idle):
    import core.operations.readiness as module
    _, service, _ = seed(tmp_path)
    assert service.run(at=DUE, query_scope=SCOPE)['status'] == 'COMPLETED'
    original = module.inventory
    scans = []

    def counted(root, *args, **kwargs):
        scans.append(root)
        return original(root, *args, **kwargs)

    monkeypatch.setattr(module, 'inventory', counted)
    result = service.run(at=DUE, query_scope=SCOPE, if_idle=if_idle)
    assert result['status'] == 'COMPLETED'
    assert result['recovery'] is None
    assert len(scans) == 1
