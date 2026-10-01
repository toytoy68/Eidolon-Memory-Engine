"""Repair views independently of which canonical writer changed their sources."""
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
from core.dossiers.projects import BEGIN, END, ProjectDossiers
from core.dossiers.reconciliation import DossierReconciler
from core.information.writes import FilesystemInformationWrites
from core.operations.readiness import recover_all
from core.operations.thread_update import FilesystemThreadUpdates
from core.threads.models import Thread
from core.threads.storage import ThreadStorage
from tests.test_project_dossiers import seed as base_seed
from tools.vm_acceptance import hashes


STAMP = '2026-10-01T19:30:00Z'


def seed(root):
    backend, storage, dossiers = base_seed(root)
    thread = replace(storage.get('thread-cooling'), created_at=STAMP, updated_at=STAMP)
    storage._atomic_write(storage._path(thread.thread_id), storage._serialize(thread))
    return backend, storage, dossiers


def open_dossiers(root):
    backend = FilesystemBackend(root / 'memory/persistent', root / 'memory/history')
    return ProjectDossiers(backend, ThreadStorage(backend.persistent_root), root / 'memory/dossiers')


def update(backend, content):
    current = backend.get('info-1')
    return FilesystemInformationWrites(backend).update(
        replace(current, content=content), previous_revision=current.revision,
        operation_id='correct', event_id='correct-event', actor='human', timestamp=STAMP)


def thread_command(backend, command, revision=1, opid='command'):
    return FilesystemThreadUpdates(backend).execute(
        'thread-cooling', command, previous_revision=revision, operation_id=opid,
        event_id=opid + '-event', actor='human', timestamp=STAMP)


def test_inspection_manifest_is_read_only_and_apply_creates_missing_view(tmp_path):
    backend, storage, dossiers = seed(tmp_path)
    reconciler = DossierReconciler(dossiers)
    before = hashes(tmp_path)
    report = reconciler.inspect()
    assert report['status'] == 'DRIFT'
    item = report['items'][0]
    assert item['status'] == 'MISSING'
    assert [(d['kind'], d['id'], d['revision']) for d in item['dependencies']] == [
        ('thread', 'thread-cooling', 1), ('information', 'info-1', 1)]
    assert all(len(d['sha256']) == 64 for d in item['dependencies'])
    assert hashes(tmp_path) == before
    assert not dossiers.root.exists()
    result = reconciler.apply()
    assert result['status'] == 'RECONCILED' and result['actions'][0]['status'] == 'CREATED'
    assert reconciler.inspect()['status'] == 'CLEAN'
    stable = hashes(tmp_path)
    assert reconciler.apply()['actions'] == []
    assert hashes(tmp_path) == stable


def test_committed_correction_refreshes_all_dependents_and_preserves_notes_exactly(tmp_path):
    backend, storage, dossiers = seed(tmp_path)
    storage.create(Thread('second-project', 'Other', 'Same source',
                          relations=[{'type': 'CONCERNS', 'target_id': 'info-1'}]))
    reconciler = DossierReconciler(dossiers)
    reconciler.apply()
    path = dossiers._path('thread-cooling')
    _, generated, _ = dossiers._parts(dossiers._read_text(path))
    prefix, suffix = 'Ma note\r\nÉté : garder.\r\n', '\r\nAprès le résumé\r\n'
    path.write_bytes((prefix + generated + suffix).encode())
    update(backend, 'Nouvelle mesure confirmée.')
    canonical = hashes(backend.persistent_root), hashes(backend.history_root)
    assert reconciler.inspect()['status'] == 'DRIFT'
    assert len(reconciler.apply()['actions']) == 2
    for identity in ('thread-cooling', 'second-project'):
        text = dossiers._path(identity).read_text()
        assert 'Nouvelle mesure confirmée.' in text and 'Une pompe à tester.' not in text
    before, _, after = dossiers._parts(dossiers._read_text(path))
    assert (before, after) == (prefix, suffix)
    assert (hashes(backend.persistent_root), hashes(backend.history_root)) == canonical


def test_new_link_then_unlink_and_delete_remove_old_excerpts(tmp_path):
    backend, storage, dossiers = seed(tmp_path)
    reconciler = DossierReconciler(dossiers)
    reconciler.apply()
    backend.store(Memory('second', content='Second apport'))
    thread_command(backend, {'kind': 'LINK', 'information_id': 'second'})
    assert reconciler.apply()['status'] == 'RECONCILED'
    assert 'Second apport' in dossiers._path('thread-cooling').read_text()
    thread_command(backend, {'kind': 'UNLINK', 'information_id': 'info-1'}, 2, 'unlink')
    backend.delete_request('info-1', 'human', 'remove', 1, 'delete-info')
    backend.approve_delete('info-1', 'delete-info')
    before = hashes(backend.history_root)
    reconciler.apply()
    text = dossiers._path('thread-cooling').read_text()
    assert 'Une pompe à tester.' not in text and 'Second apport' in text
    assert backend.get('info-1') is None and hashes(backend.history_root) == before


def test_deleted_thread_is_found_from_existing_view_and_scrubbed(tmp_path):
    backend, storage, dossiers = seed(tmp_path)
    reconciler = DossierReconciler(dossiers)
    reconciler.apply()
    path = dossiers._path('thread-cooling')
    path.write_text('Ma note privée\n' + path.read_text())
    storage.delete('thread-cooling', previous_revision=1, operation_id='delete-project')
    assert reconciler.inspect()['items'][0]['status'] == 'ORPHANED'
    assert reconciler.apply()['actions'][0]['status'] == 'SOURCE_REMOVED'
    text = path.read_text()
    assert 'Une pompe à tester.' not in text and 'Ma note privée' in text
    assert 'Thread source absent' in text and storage.get('thread-cooling') is None
    assert reconciler.apply()['status'] == 'CLEAN'


def test_current_revision_with_direct_source_edit_is_still_detected(tmp_path):
    backend, storage, dossiers = seed(tmp_path)
    reconciler = DossierReconciler(dossiers)
    reconciler.apply()
    old = reconciler.inspect()['items'][0]
    path = backend._path('info-1')
    path.write_text(path.read_text().replace('Une pompe à tester.', 'Mesure modifiée.'))
    changed = reconciler.inspect()['items'][0]
    assert changed['status'] == 'STALE' and changed['source_digest'] != old['source_digest']
    assert backend.get('info-1').revision == 1
    reconciler.apply()
    assert 'Mesure modifiée.' in dossiers._path('thread-cooling').read_text()


def test_damaged_notes_boundary_blocks_whole_batch_before_publication(tmp_path):
    backend, storage, dossiers = seed(tmp_path)
    reconciler = DossierReconciler(dossiers)
    reconciler.apply()
    storage.create(Thread('aaa-new', 'New', 'Not published on blocked batch'))
    path = dossiers._path('thread-cooling')
    path.write_text(path.read_text().replace(END, ''))
    before = hashes(tmp_path)
    result = reconciler.apply()
    assert result['status'] == 'BLOCKED' and result['actions'] == []
    assert hashes(tmp_path) == before
    assert not dossiers._path('aaa-new').exists()


def test_unmanaged_markdown_is_preserved_and_never_adopted(tmp_path):
    _, _, dossiers = seed(tmp_path)
    dossiers.root.mkdir()
    notes = dossiers.root / 'notes.md'
    notes.write_text('My own notes')
    reconciler = DossierReconciler(dossiers)
    assert reconciler.apply()['status'] == 'RECONCILED'
    assert notes.read_text() == 'My own notes'
    assert reconciler.inspect()['items'][0]['status'] == 'UNMANAGED'
    dossiers._path('thread-cooling').write_text('Handwritten project, no markers')
    assert reconciler.apply()['status'] == 'BLOCKED'
    assert dossiers._path('thread-cooling').read_text() == 'Handwritten project, no markers'


def test_unfinished_canonical_write_requires_recovery_before_reconciliation(tmp_path, monkeypatch):
    backend, _, dossiers = seed(tmp_path)
    reconciler = DossierReconciler(dossiers)
    reconciler.apply()
    with monkeypatch.context() as patch:
        from core.events.filesystem import FilesystemEventRepository
        patch.setattr(FilesystemEventRepository, 'save', lambda *a: (_ for _ in ()).throw(RuntimeError('stop')))
        with pytest.raises(RuntimeError):
            update(backend, 'Interrupted correction')
    before = hashes(tmp_path)
    assert reconciler.apply()['status'] == 'BLOCKED'
    assert hashes(tmp_path) == before
    assert recover_all(tmp_path)['readiness']['ready']
    assert reconciler.apply()['status'] == 'RECONCILED'
    assert 'Interrupted correction' in dossiers._path('thread-cooling').read_text()


@pytest.mark.parametrize('boundary', ['before', 'after'])
def test_interrupted_batch_rescans_remaining_work_without_replaying_sources(tmp_path, monkeypatch, boundary):
    backend, storage, dossiers = seed(tmp_path)
    storage.create(Thread('z-last', 'Last', 'Another view'))
    reconciler = DossierReconciler(dossiers)
    # Initialize only the technical lock so canonical byte comparison is exact.
    from core.persistence import exclusive_write
    with exclusive_write(backend.persistent_root):
        pass
    canonical = hashes(backend.persistent_root), hashes(backend.history_root)
    from core.dossiers import projects
    original = projects.atomic_write_text
    def stop(path, text):
        if boundary == 'after':
            original(path, text)
        raise RuntimeError('interrupted')
    with monkeypatch.context() as patch:
        patch.setattr(projects, 'atomic_write_text', stop)
        with pytest.raises(RuntimeError):
            reconciler.apply()
    state = reconciler.inspect()
    assert state['status'] == 'DRIFT'
    assert [i['status'] for i in state['items']] == (['MISSING', 'MISSING'] if boundary == 'before' else ['CURRENT', 'MISSING'])
    assert len(reconciler.apply()['actions']) == (2 if boundary == 'before' else 1)
    assert (hashes(backend.persistent_root), hashes(backend.history_root)) == canonical


def crash_after_first_view(root):
    from core.dossiers import projects
    original = projects.atomic_write_text
    def stop(path, text):
        original(path, text)
        os._exit(74)
    projects.atomic_write_text = stop
    DossierReconciler(open_dossiers(Path(root))).apply()


def test_process_exit_releases_locks_and_next_process_finishes_remaining_views(tmp_path):
    _, storage, dossiers = seed(tmp_path)
    storage.create(Thread('z-last', 'Last', 'Another view'))
    child = multiprocessing.get_context('spawn').Process(target=crash_after_first_view, args=(str(tmp_path),))
    child.start()
    try:
        child.join(15)
        assert child.exitcode == 74
    finally:
        if child.is_alive():
            child.terminate()
            child.join()
    command = [sys.executable, '-B', '-m', 'core.dossiers.cli', '--root', str(tmp_path), 'reconcile', '--apply']
    result = subprocess.run(command, text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert [item['thread_id'] for item in report['actions']] == ['z-last']
    assert DossierReconciler(dossiers).inspect()['status'] == 'CLEAN'


def test_cli_inspect_never_creates_files_and_apply_recomputes_current_state(tmp_path):
    command = [sys.executable, '-B', '-m', 'core.dossiers.cli', '--root', str(tmp_path), 'reconcile']
    empty = subprocess.run(command, text=True, capture_output=True)
    assert empty.returncode == 0 and json.loads(empty.stdout)['status'] == 'CLEAN'
    assert list(tmp_path.iterdir()) == []
    backend, _, dossiers = seed(tmp_path)
    before = hashes(tmp_path)
    missing = subprocess.run(command, text=True, capture_output=True)
    assert missing.returncode == 1 and json.loads(missing.stdout)['status'] == 'DRIFT'
    assert hashes(tmp_path) == before
    update(backend, 'Changed after inspection')
    result = subprocess.run([*command, '--apply'], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert 'Changed after inspection' in dossiers._path('thread-cooling').read_text()


def test_symlink_dossier_blocks_without_touching_its_target(tmp_path):
    _, _, dossiers = seed(tmp_path)
    dossiers.root.mkdir()
    external = tmp_path / 'external.md'
    external.write_text('Unrelated data')
    dossiers._path('thread-cooling').symlink_to(external)
    result = DossierReconciler(dossiers).apply()
    assert result['status'] == 'BLOCKED' and result['actions'] == []
    assert external.read_text() == 'Unrelated data'


@pytest.mark.parametrize('command, expected', [
    ({'kind': 'DETAILS', 'fields': {'objective': 'Nouvel objectif'}}, 'Nouvel objectif'),
    ({'kind': 'ACTION_STATUS', 'action_id': 'test-pump', 'status': 'COMPLETED'}, '[COMPLETED]'),
])
def test_project_changes_outside_routing_refresh_the_view(tmp_path, command, expected):
    backend, _, dossiers = seed(tmp_path)
    reconciler = DossierReconciler(dossiers)
    reconciler.apply()
    thread_command(backend, command)
    assert reconciler.inspect()['items'][0]['status'] == 'STALE'
    assert reconciler.apply()['status'] == 'RECONCILED'
    assert expected in dossiers._path('thread-cooling').read_text()


def test_unknown_journal_blocks_even_when_project_sources_look_current(tmp_path):
    backend, _, dossiers = seed(tmp_path)
    reconciler = DossierReconciler(dossiers)
    reconciler.apply()
    unknown = backend.history_root / 'operations/unknown-v9'
    unknown.mkdir(parents=True)
    (unknown / 'pending.json').write_text('{}')
    before = hashes(tmp_path)
    report = reconciler.apply()
    assert report['status'] == 'BLOCKED' and report['issues']
    assert hashes(tmp_path) == before


def competing_reconciliation(root, slot, ready, start):
    dossiers = open_dossiers(Path(root))
    ready.set()
    if not start.wait(10):
        raise RuntimeError('start timeout')
    report = DossierReconciler(dossiers).apply()
    (Path(root) / f'result-{slot}.json').write_text(json.dumps(report))


def test_two_reconcilers_serialize_and_do_not_republish_current_views(tmp_path):
    _, _, dossiers = seed(tmp_path)
    context = multiprocessing.get_context('spawn')
    start = context.Event()
    ready = [context.Event(), context.Event()]
    children = [context.Process(target=competing_reconciliation,
                args=(str(tmp_path), i, ready[i], start)) for i in range(2)]
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
    results = [json.loads((tmp_path / f'result-{i}.json').read_text()) for i in range(2)]
    assert sorted(result['status'] for result in results) == ['CLEAN', 'RECONCILED']
    assert sum(len(result['actions']) for result in results) == 1
    assert DossierReconciler(dossiers).inspect()['status'] == 'CLEAN'
