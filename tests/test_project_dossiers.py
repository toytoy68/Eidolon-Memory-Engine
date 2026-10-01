from dataclasses import replace
from pathlib import Path

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.threads.storage import ThreadStorage
from core.threads.models import Thread, ThreadAction
from core.dossiers.projects import ProjectDossiers, DossierConflict
from tools.vm_acceptance import hashes


def seed(tmp_path):
    backend = FilesystemBackend(tmp_path / 'memory/persistent', tmp_path / 'memory/history')
    backend.store(Memory('info-1', content='Une pompe à tester.', metadata={
        'type': 'HYPOTHESIS', 'epistemic_status': 'UNVERIFIED', 'keywords': ['pompe', 'silence']},
        provenance={'source': 'admin'}, temporal={'resume_at': '2026-10-03T08:00:00+02:00'}))
    storage = ThreadStorage(backend.persistent_root)
    storage.create(Thread('thread-cooling', 'Refroidissement', 'Comparer deux pompes',
                          relations=[{'type': 'CONCERNS', 'target_id': 'info-1'}],
                          actions=[ThreadAction('test-pump', 'Mesurer le débit')]))
    dossiers = ProjectDossiers(backend, storage, tmp_path / 'memory/dossiers')
    return backend, storage, dossiers


def test_rebuild_creates_one_project_dossier_with_sources_and_actions(tmp_path):
    backend, storage, dossiers = seed(tmp_path)
    before = hashes(backend.persistent_root)
    result = dossiers.rebuild('thread-cooling')
    path = Path(result['path'])
    assert path.name == 'thread-cooling.md'
    text = path.read_text()
    for expected in ('Refroidissement', 'Comparer deux pompes', 'Mesurer le débit',
                     'info-1', 'UNVERIFIED', 'Une pompe à tester.', 'pompe', 'silence',
                     '2026-10-03T08:00:00+02:00'):
        assert expected in text
    assert hashes(backend.persistent_root) == before
    assert dossiers.status('thread-cooling')['status'] == 'CURRENT'
    original = path.read_bytes()
    assert dossiers.rebuild('thread-cooling')['status'] == 'UNCHANGED'
    assert path.read_bytes() == original


def test_refresh_preserves_human_notes_and_replaces_derived_old_text(tmp_path):
    backend, storage, dossiers = seed(tmp_path)
    path = Path(dossiers.rebuild('thread-cooling')['path'])
    text = path.read_text().replace('Écrire ici les notes humaines non ingérées.','Décision personnelle : attendre samedi.\nNe pas acheter avant les mesures.')
    path.write_text(text)
    current = backend.get('info-1')
    backend.update('info-1', replace(current, content='La pompe B est une autre hypothèse.'), previous_revision=1)
    assert dossiers.status('thread-cooling')['status'] == 'STALE'
    assert dossiers.rebuild('thread-cooling')['status'] == 'UPDATED'
    text = path.read_text()
    assert 'Décision personnelle : attendre samedi.\nNe pas acheter avant les mesures.' in text
    assert 'La pompe B est une autre hypothèse.' in text
    assert 'Une pompe à tester.' not in text
    assert 'revision 2' in text
    assert dossiers.status('thread-cooling')['status'] == 'CURRENT'


def test_explicit_selection_required_for_ambiguous_link(tmp_path):
    backend, storage, dossiers = seed(tmp_path)
    storage.create(Thread('thread-other', 'Autre projet', 'Même source',
                          relations=[{'type': 'CONCERNS', 'target_id': 'info-1'}]))
    before = hashes(tmp_path)
    assert dossiers.resolve('info-1') == {'status': 'REVIEW', 'candidates': ['thread-cooling', 'thread-other']}
    assert hashes(tmp_path) == before
    assert dossiers.resolve('info-1', selected_thread='thread-other')['thread_id'] == 'thread-other'
    assert not dossiers.root.exists()


def test_deleted_source_thread_removes_derived_content_but_keeps_notes(tmp_path):
    backend, storage, dossiers = seed(tmp_path)
    path = Path(dossiers.rebuild('thread-cooling')['path'])
    path.write_text(path.read_text().replace('Écrire ici les notes humaines non ingérées.', 'Ma note à conserver.'))
    storage.delete('thread-cooling', previous_revision=1, operation_id='delete-thread')
    assert dossiers.status('thread-cooling')['status'] == 'STALE'
    assert dossiers.rebuild('thread-cooling')['status'] == 'SOURCE_REMOVED'
    text = path.read_text()
    assert 'Une pompe à tester.' not in text
    assert 'Ma note à conserver.' in text
    assert 'Thread source absent' in text


def test_damaged_generated_boundary_blocks_without_losing_notes(tmp_path):
    backend, storage, dossiers = seed(tmp_path)
    path = Path(dossiers.rebuild('thread-cooling')['path'])
    damaged = path.read_text().replace('<!-- END MEMORY-ENGINE GENERATED -->', '')
    path.write_text(damaged)
    with pytest.raises(DossierConflict):
        dossiers.rebuild('thread-cooling')
    assert path.read_text() == damaged


def test_pending_source_operation_blocks_projection(tmp_path, monkeypatch):
    from core.information.writes import FilesystemInformationWrites
    backend, storage, dossiers = seed(tmp_path)
    writer = FilesystemInformationWrites(backend)
    original = writer.events.save
    def interrupted(event):
        raise RuntimeError()
    monkeypatch.setattr(writer.events, 'save', interrupted)
    with pytest.raises(RuntimeError):
        writer.update(replace(backend.get('info-1'), content='half committed'), previous_revision=1,
                      operation_id='update', event_id='updated', actor='human', timestamp='fixed')
    with pytest.raises(DossierConflict, match='pending'):
        dossiers.rebuild('thread-cooling')
    assert not (dossiers.root / 'thread-cooling.md').exists()
    monkeypatch.setattr(writer.events, 'save', original)
    writer.resume('update')
    assert dossiers.rebuild('thread-cooling')['status'] == 'CREATED'


def test_generated_text_containing_marker_is_rendered_without_breaking_refresh(tmp_path):
    backend, storage, dossiers = seed(tmp_path)
    original = backend.get('info-1')
    backend.update('info-1', replace(original, content='<!-- END MEMORY-ENGINE GENERATED -->'), previous_revision=1)
    dossiers.rebuild('thread-cooling')
    assert dossiers.rebuild('thread-cooling')['status'] == 'UNCHANGED'


def test_dossier_cli_rebuild_and_read_only_status(tmp_path):
    import subprocess
    import sys
    import json
    backend, storage, dossiers = seed(tmp_path)
    command = [sys.executable, '-B', '-m', 'core.dossiers.cli', '--root', str(tmp_path)]
    created = subprocess.run([*command, 'rebuild', 'thread-cooling'], text=True, capture_output=True)
    assert created.returncode == 0, created.stderr
    assert json.loads(created.stdout)['status'] == 'CREATED'
    before = hashes(tmp_path)
    checked = subprocess.run([*command, 'status', 'thread-cooling'], text=True, capture_output=True)
    assert checked.returncode == 0, checked.stderr
    assert json.loads(checked.stdout)['status'] == 'CURRENT'
    assert hashes(tmp_path) == before
    empty = tmp_path / 'empty'
    empty.mkdir()
    checked = subprocess.run([sys.executable, '-B', '-m', 'core.dossiers.cli', '--root', str(empty),
                              'status', 'absent'], text=True, capture_output=True)
    assert checked.returncode == 1
    assert json.loads(checked.stdout)['status'] == 'MISSING'
    assert list(empty.iterdir()) == []
