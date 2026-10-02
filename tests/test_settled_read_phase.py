"""Full audits reused only inside a locked, disposable derived-read phase."""
from contextlib import ExitStack
from dataclasses import replace
import json

import pytest

from core.dossiers.projects import DossierConflict
from core.information.write_journal import InformationWriteJournal
from core.operations.read_phase import settled_read_phase, has_settled_audit
from core.operations.readiness import check_readiness
from core.persistence import atomic_write_text, exclusive_write
from tests.test_maintenance_pass import seed
from tests.test_routing_lifecycle import STAMP, DUE, SCOPE


def locks(service):
    stack = ExitStack()
    stack.enter_context(exclusive_write(service.backend.persistent_root))
    stack.enter_context(exclusive_write(service.storage.threads_root))
    return stack


def test_audit_reused_across_projects_and_catalogue_without_lightweight_validation(tmp_path, monkeypatch):
    backend, service, _ = seed(tmp_path)
    original = InformationWriteJournal.read
    calls = []
    def counted(self, identity):
        calls.append(identity)
        return original(self, identity)
    monkeypatch.setattr(InformationWriteJournal, 'read', counted)
    with locks(service), settled_read_phase(tmp_path):
        assert not has_settled_audit(tmp_path)
        assert check_readiness(tmp_path)['ready']
        audited = list(calls)
        assert audited
        service.dossiers.inspect()
        service.dossiers.dossiers.status('project')
        service.catalogue.status()
        assert calls == audited
    assert not has_settled_audit(tmp_path)
    assert check_readiness(tmp_path)['ready']
    assert len(calls) == 2 * len(audited)


@pytest.mark.parametrize('held', ['none', 'persistent'])
def test_scope_cannot_reuse_audit_without_both_existing_source_locks(tmp_path, held):
    _, service, _ = seed(tmp_path)
    with ExitStack() as stack:
        if held == 'persistent':
            stack.enter_context(exclusive_write(service.backend.persistent_root))
        with pytest.raises(RuntimeError, match='locks'):
            with settled_read_phase(tmp_path):
                pass


def test_cached_report_is_not_mutable_by_the_caller(tmp_path):
    _, service, _ = seed(tmp_path)
    with locks(service), settled_read_phase(tmp_path):
        first = check_readiness(tmp_path)
        first['ready'] = False
        first['issues'].append({'reason': 'injected'})
        second = check_readiness(tmp_path)
        assert second['ready'] and second['issues'] == []


@pytest.mark.parametrize('alias', [False, True])
def test_canonical_publication_invalidates_a_successful_audit(tmp_path, alias):
    backend, service, _ = seed(tmp_path)
    path = service.lifecycle.journal.path('bad')
    if alias:
        (tmp_path / 'alias-parent').mkdir()
        path = tmp_path / 'alias-parent/..' / path.relative_to(tmp_path)
    with locks(service), settled_read_phase(tmp_path):
        assert check_readiness(tmp_path)['ready']
        atomic_write_text(path, '{broken')
        assert not has_settled_audit(tmp_path)
        assert not check_readiness(tmp_path)['ready']
        assert not has_settled_audit(tmp_path)


def test_derived_publication_keeps_audit_but_current_source_is_still_re_read(tmp_path):
    backend, service, _ = seed(tmp_path)
    with locks(service), settled_read_phase(tmp_path):
        assert check_readiness(tmp_path)['ready']
        path = service.dossiers.dossiers._path('project')
        atomic_write_text(path, path.read_text() + '\nNew human note.\n')
        assert has_settled_audit(tmp_path)
        memory = backend.get('second')
        backend.update('second', replace(memory, content='New current measurement'), 1)
        assert not has_settled_audit(tmp_path)
        assert service.dossiers.apply()['status'] == 'RECONCILED'
        text = path.read_text()
        assert 'New current measurement' in text and 'New human note.' in text


def test_no_cache_survives_exception_or_next_pass_unknown_format(tmp_path):
    _, service, trigger = seed(tmp_path)
    with pytest.raises(RuntimeError):
        with locks(service), settled_read_phase(tmp_path):
            assert check_readiness(tmp_path)['ready']
            raise RuntimeError('stop')
    assert not has_settled_audit(tmp_path)
    path = service.lifecycle.journal.path(trigger)
    data = json.loads(path.read_text())
    path.write_text(json.dumps(dict(data, format_version=999)))
    assert service.run(at=STAMP, query_scope=SCOPE)['status'] == 'BLOCKED'


def test_final_maintenance_audit_is_fresh_after_derived_publication(tmp_path, monkeypatch):
    backend, service, _ = seed(tmp_path)
    def corrupt(stage):
        if stage == 'after_catalogue':
            # Deliberately bypass the publication hook: the final phase must
            # still start a fresh audit, not trust the previous phase's proof.
            service.lifecycle.journal.path('bad').write_text('{bad')
    monkeypatch.setattr(service, '_checkpoint', corrupt)
    result = service.run(at=DUE, query_scope=SCOPE)
    assert result['status'] == 'BLOCKED' and result['stage'] == 'verification'
    assert not result['verification']['readiness']['ready']
    assert backend.get('second').revision == 2


def test_successful_audit_does_not_leak_into_another_engine(tmp_path):
    first, second = tmp_path / 'one', tmp_path / 'two'
    _, one, _ = seed(first)
    _, two, _ = seed(second)
    two.lifecycle.journal.path('bad').write_text('{bad')
    with locks(one), settled_read_phase(first):
        assert check_readiness(first)['ready']
        assert not has_settled_audit(second)
        assert not check_readiness(second)['ready']


def test_standalone_dossier_guard_remains_active_after_optimized_batch(tmp_path, monkeypatch):
    backend, service, _ = seed(tmp_path)
    assert service.run(at=STAMP)['status'] == 'COMPLETED'
    from core.routing.execution import RoutingExecutor
    executor = RoutingExecutor(backend)
    executor.journal.root.mkdir(parents=True, exist_ok=True)
    executor.journal.path('bad').write_text('{bad')
    with pytest.raises(DossierConflict):
        service.dossiers.dossiers.rebuild('project')


def waiting_writer(root, entered, finished):
    from pathlib import Path
    from core.backend.filesystem import FilesystemBackend
    root = Path(root)
    backend = FilesystemBackend(root / 'memory/persistent', root / 'memory/history')
    current = backend.get('second')
    entered.set()
    backend.update('second', replace(current, content='Other process correction'), 1)
    finished.set()


def test_other_process_waits_for_read_phase_then_next_pass_sees_its_correction(tmp_path):
    import multiprocessing
    backend, service, _ = seed(tmp_path)
    context = multiprocessing.get_context('spawn')
    entered, finished = context.Event(), context.Event()
    child = context.Process(target=waiting_writer, args=(str(tmp_path), entered, finished))
    try:
        with locks(service), settled_read_phase(tmp_path):
            assert check_readiness(tmp_path)['ready']
            child.start()
            assert entered.wait(10)
            assert not finished.wait(0.1)
            assert backend.get('second').revision == 1
            assert service.dossiers.inspect()['status'] == 'CLEAN'
        child.join(15)
        assert child.exitcode == 0 and finished.is_set()
        result = service.run(at=STAMP, query_scope=SCOPE)
        assert result['status'] == 'COMPLETED' and result['dossiers']['actions']
        assert 'Other process correction' in service.dossiers.dossiers._path('project').read_text()
        assert backend.get('second').revision == 2
    finally:
        if child.pid is not None and child.is_alive():
            child.terminate()
            child.join()


def test_cached_audit_cannot_hide_a_symlink_before_parent_component(tmp_path):
    _, service, _ = seed(tmp_path)
    (tmp_path / 'outside').mkdir()
    (tmp_path / 'jump').symlink_to(tmp_path / 'outside', target_is_directory=True)
    with locks(service), settled_read_phase(tmp_path):
        assert check_readiness(tmp_path)['ready']
        with pytest.raises(ValueError, match='symlink'):
            check_readiness(tmp_path / 'jump/..')
